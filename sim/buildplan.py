"""Build sequencing for the physical DTS-02.

Turns the hole-level layout (sim/layout.py) into the spec's Section 11.1
wiring sequence: which ICs, parts and wires go down in each bring-up phase,
which inputs that phase leaves floating (with the temporary straps the spec
prescribes for them), a wire cut list, an orderable BOM, and the wiring delta
for fitting a 28C256 EEPROM as a development ROM in place of the OTP part.
Everything is derived from the layout and the netlist, so it tracks the spec;
`python3 -m sim wiring` writes wiring/BUILD.md and wiring/BOM.md.
"""

import csv
import os
import re
from collections import Counter, defaultdict

from . import layout as LY
from .board import GND, VCC
from .layout import RAILS, fmt, strip_key, wire_mm
from .specdoc import spec_text

# ---------------------------------------------------------------------------
# phases (spec Section 11.1), with the ICs each one fits
# ---------------------------------------------------------------------------

PHASES = [
    dict(key="power", title="Power only", step="Section 11.1 step 1", ics=[],
         goal="Regulated 5 V on every rail with nothing else fitted.",
         checks=[
             "Build the fused regulator fixture (Section 5.1) or use a current-limited bench supply on "
             "PWR:VCC / PWR:GND. Start with a low current limit and raise it only as stages are added.",
             "DMM: 4.85–5.15 V between the + and − rails of every board, on both halves of every rail "
             "(the halves are joined only by the bridge wires in the table above).",
             "Nothing connects the battery-input side (VIN, VBAT_SW) to a 5 V rail.",
         ]),
    dict(key="clock", title="Clock and reset", step="Section 11.1 step 2",
         ics=["U5", "U6", "U7", "U11", "U45"],
         goal="A clean master clock, the six Johnson states, and the two-stage reset release. "
              "The supervisor U42 joins the power fixture now.",
         checks=[
             "Scope MASTER_CLK at U5 pin 2 ({U5.2}): ≤600 kHz with clean Schmitt edges. Change the RC only "
             "with power off; the spec's 10 kΩ / 560 pF lands anywhere in 76–530 kHz (Section 5.3).",
             "Scope Q_A (U6 pin 5, {U6.5}), Q_B (U6 pin 9, {U6.9}) and Q_C (U45 pin 9, {U45.9}): "
             "the sequence 000→100→110→111→011→001 repeating, with no stray state (Section 5.5).",
             "PHI2 at the empty U1 pin 37 hole ({U1.37}): MASTER/6, ≤100 kHz, rise and fall ≤5 ns "
             "(Section 5.4). Use a ground spring on the probe.",
             "Power-up: COLD_CLEAR_N (U5 pin 6, {U5.6}) releases before CPU_RESET_N (U11 pin 8, {U11.8}) "
             "with at least two PHI2 cycles in between; expect roughly 30–150 ms. The CPU RESET button "
             "drops CPU_RESET_N only, never COLD_CLEAR_N.",
             "Reference waveform: `python3 -m sim run idle --vcd clock.vcd`, then view MASTER_CLK, Q_A, Q_B, "
             "Q_C, PHI2, COLD_CLEAR_N and CPU_RESET_N in GTKWave.",
         ]),
    dict(key="core", title="CPU, ROM and bus interface", step="Section 11.1 step 3",
         ics=["U1", "U3", "U4", "U44", "U8", "U9", "U10", "U12", "U13", "U18"],
         goal="The CPU fetches from ROM through the windowed bus interface, and the Section 11.2 "
              "handoff measurements pass before any SRAM is trusted.",
         note="U18 is fitted here although the spec's step 3 text lists only U8–U13: in revision 0.4 "
              "U18 gate 2 generates RD_WIN_N, the ROM's output enable, so nothing reads without it.",
         checks=[
             "`python3 -m sim rom` writes `_build/rom/dts02_diag.bin`. Program it, read it back, and compare "
             "the SHA-256 with the value printed (it must equal the spec's Section 11.3 hash). Fit the ROM "
             "with the notch toward row 1 at {U3.1}.",
             "Logic analyzer or scope on A0–A15 and C_D: after CPU RESET releases, reads of $FFFC and $FFFD, "
             "then fetches from $8000 and the loop at $800A (Section 11.3).",
             "Run the eight Section 11.2 handoff checks (RD_WIN_N at U18 pin 6, {U18.6}; RWB_CYCLE at "
             "U45 pin 5, {U45.5}; U4 and U44 enables; rise times of released P_D and C_D lines). "
             "Expected values: `python3 -m sim handoff` and `python3 -m sim diag --vcd core.vcd`.",
             "Without SRAM the diagnostic's STA $0200 writes go nowhere; that is expected.",
         ]),
    dict(key="ram", title="SRAM", step="Section 11.1 step 4", ics=["U2"],
         goal="Writes and reads at $0200 through the same windows, then the handoff checks again with RAM "
              "as a P_D driver.",
         checks=[
             "Diagnostic ROM: $0200 follows the raw DIP byte (all switches open = $FF, all closed = $00). "
             "Probe RAM_WE_N (U12 pin 11, {U12.11}) and RAM_CE_N (U10 pin 3, {U10.3}) together.",
             "Repeat the Section 11.2 checks for the RAM write → RAM read and RAM read → ROM read transitions.",
             "The walking address/data test lives in the test ROM (scenario `ram`, below) and reports on the "
             "display, so it becomes usable after the display phases; until then observe the bus directly.",
         ]),
    dict(key="io", title="Input and GPIO", step="Section 11.1 step 5",
         ics=["U14", "U15", "U16", "U17"],
         goal="The DIP byte and keys read back, and the GPIO latch takes exactly one strobe per store.",
         checks=[
             "Program `_build/rom/dts02_test.bin` (the boot/test ROM). With all DIP poles open it boots to "
             "the idle loop; `python3 -m sim rom` prints its hash and writes `dts02_test.sym`.",
             "Diagnostic ROM or test ROM: $7F00 reads the raw byte (closed pole = 0); $7F01 bits 0–4 go high "
             "while ENTER, NEXT, BACK, APPROVE, ABORT are pressed; bits 5–7 read 0 with the straps below.",
             "Scope WR_GPIO_N (U12 pin 8, {U12.8}): exactly one rising edge per STA $7F02, two master periods "
             "before PHI2 falls. DISPLAY_OE_N (U18 pin 12, {U18.12}) stays high after reset.",
         ]),
    dict(key="digit0", title="Display fanout and the first digit", step="Section 11.1 step 6 (first digit)",
         ics=["U19", "U20", "U21"],
         goal="One digit proves the segment mapping, the 3.3 kΩ current and room-light legibility before "
              "sixteen are soldered.",
         checks=[
             "Test ROM scenario `font` (DIP byte 8): digit 0 shows `0`. Scenario `lamp` (DIP byte 9): all "
             "eight segments of digit 0 on; measure about 0.9 mA per segment.",
             "Check the SC56-11 pin mapping (Section 8) on this digit before soldering the rest of the panel.",
         ]),
    dict(key="display", title="Remaining fifteen digits", step="Section 11.1 step 6 (rest)",
         ics=[f"U{n}" for n in range(22, 37)],
         goal="The full panel, then the supervisor rail check under full display load.",
         checks=[
             "Scenario `font`: `0123456789AbCdEF` left to right. Scenario `lamp`: all 128 segments.",
             "With all segments lit: rail at U42's VDD lead ≥4.85 V and at the farthest board ≥4.75 V; "
             "no COLD_CLEAR_N activity during a display-change soak (Section 5.2). Measure the regulator tab "
             "temperature (Section 5.1).",
             "Scenario `ram` (DIP byte 1): the display shows `-` followed by the error count in hex; `-00` "
             "passes the Section 11.1 step 4 walking address/data test.",
         ]),
    dict(key="locks", title="Bank locks and fault latch (BB9)", step="Section 11.1 step 7",
         ics=["U37", "U38", "U39", "U40", "U41"],
         goal="Hardware bank locks, the fault latch and the three status LEDs. Remove every strap listed "
              "under 'remove' below before power-up.",
         checks=[
             "Run the Section 11.4 table with the test ROM scenarios `msg_fault` (2), `res_fault` (3), "
             "`msg_frozen` (4), `record_ok` (5), `record_bad` (6) and `mirrors` (7), pressing CPU RESET where "
             "the table says. Expected states: `python3 -m sim run msg_fault --reset` and so on.",
             "A faulted board blanks the panel and lights the red LED; only a cold clear recovers it.",
         ]),
]

PHASE_INDEX = {p["key"]: i for i, p in enumerate(PHASES)}
IC_PHASE = {u: p["key"] for p in PHASES for u in p["ics"]}

# straps the spec prescribes while the lock board is absent (Sections 7.2, 8, 9)
SPEC_STRAPS = {
    "WRITE_BLOCK": (GND, "Section 9: tie WRITE_BLOCK low while BB9 is absent"),
    "FAULT_N": (VCC, "Section 8, U18 pin 13: tie +5 V if the security board is absent"),
    "MESSAGE_LOCK": (GND, "Section 8, U15: tie the three status inputs to GND if BB9 is absent"),
    "RESULT_LOCK": (GND, "Section 8, U15: tie the three status inputs to GND if BB9 is absent"),
    "FAULT": (GND, "Section 8, U15: tie the three status inputs to GND if BB9 is absent"),
}

_PART_RULES = [
    (r"C_BYP_(U\d+)", lambda m: IC_PHASE[m.group(1)]),
    (r"C_BULK_BB\d+", "power"),
    (r"U43|C_IN[12]|C_OUT[12]|R_BLEED|D_REV", "power"),
    (r"U42|R_POR|C_U42", "clock"),
    (r"R_OSC|C_OSC|R_RST|C_RST|R_RSTD|D_RST|R_RSTBTN|SW_RESET", "clock"),
    (r"R_CD\d|R_PD\d|R_CPU_\w+", "core"),
    (r"R_SW\d|DIP\d|R_KEY_\w+|C_KEY_\w+|R_KEYD_\w+|SW_(ENTER|NEXT|BACK|APPROVE|ABORT)", "io"),
    (r"R_(SRCLK|OE|RCLK|SRCLR|DATA)\d", "digit0"),
    (r"R_U21_\w+|D0", "digit0"),
    (r"R_U(2[2-9]|3[0-6])_\w+|D([1-9]|1[0-5])", "display"),
    (r"R_LED_\w+|LED_\w+", "locks"),
]

_BEHAVIOURAL_PHASE = {"OSC": "clock", "OSC_RC_NODE": "clock", "RESET_RC_MODEL": "clock",
                      "RESET_BTN": "clock", "U42": "clock"}


def part_phase(ref):
    for pat, ph in _PART_RULES:
        m = re.fullmatch(pat, ref)
        if m:
            return ph(m) if callable(ph) else ph
    raise KeyError(f"no build phase for part {ref}")


def sim_part_phase(name):
    """Phase of a simulator part (ICs, behavioural stand-ins, resistors, digits, LEDs)."""
    if name in _BEHAVIOURAL_PHASE:
        return _BEHAVIOURAL_PHASE[name]
    if re.fullmatch(r"U\d+", name):
        return IC_PHASE[name]
    if re.fullmatch(r"DIPSW\d|KEYSW_\w+", name):
        return "io"
    return part_phase(name)


# ---------------------------------------------------------------------------
# assignment
# ---------------------------------------------------------------------------

def plan(L):
    """Assign every IC, part and wire of layout L to a phase.

    A wire goes in the first phase in which both of its end strips exist: a
    strip exists when a component on it has been fitted; rails exist from the
    power phase; a landing strip that carries only wires exists as soon as its
    earliest neighbour does."""
    idx = PHASE_INDEX
    strip_phase = {}

    def note(h, ph):
        k = strip_key(h)
        strip_phase[k] = min(strip_phase.get(k, 99), ph)

    for (u, pin), h in L.pin_hole.items():
        note(h, idx[IC_PHASE[u]])
    for it in L.items:
        ph = idx[part_phase(it["ref"])]
        for h, _ in it["leads"]:
            note(h, ph)
    for h1, h2, _ in L.wires:
        for h in (h1, h2):
            if h[1] in RAILS:
                note(h, idx["power"])
    changed = True
    while changed:                       # landing strips inherit their earliest neighbour
        changed = False
        for h1, h2, _ in L.wires:
            k1, k2 = strip_key(h1), strip_key(h2)
            a, b = strip_phase.get(k1), strip_phase.get(k2)
            if a is None and b is not None:
                strip_phase[k1] = b
                changed = True
            elif b is None and a is not None:
                strip_phase[k2] = a
                changed = True
    out = {p["key"]: dict(ics=[], parts=[], wires=[]) for p in PHASES}
    for p in PHASES:
        out[p["key"]]["ics"] = list(p["ics"])
    for it in L.items:
        out[part_phase(it["ref"])]["parts"].append(it)
    unassigned = []
    for w in L.wires:
        a, b = strip_phase.get(strip_key(w[0])), strip_phase.get(strip_key(w[1]))
        if a is None or b is None:
            unassigned.append(w)
            continue
        out[PHASES[max(a, b)]["key"]]["wires"].append(w)
    return out, unassigned


def floating_inputs(L, sim, phase_key):
    """Inputs of fitted parts whose every driver arrives in a later phase and
    that no fitted pull resistor holds: [(part, pin, net, arrives_phase)]."""
    P = PHASE_INDEX[phase_key]
    held = set()
    for it in L.items:
        if it["kind"] == "R" and len(it["leads"]) == 2 and PHASE_INDEX[part_phase(it["ref"])] <= P:
            nets = {n for _, n in it["leads"]}
            if nets & {VCC, GND}:
                held |= nets - {VCC, GND}
    drivers = defaultdict(list)
    for p in sim.parts.values():
        for pin, role in p.roles.items():
            net = p.pins.get(pin)
            if net is not None and role in ("out", "tri", "behavioural"):
                drivers[net.name].append(PHASE_INDEX[sim_part_phase(p.name)])
    out = []
    for p in sim.parts.values():
        if PHASE_INDEX[sim_part_phase(p.name)] > P:
            continue
        for pin, role in p.roles.items():
            net = p.pins.get(pin)
            if role != "in" or net is None or net.name in (VCC, GND) or net.name in held:
                continue
            if any(d <= P for d in drivers[net.name]):
                continue
            arrives = min(drivers[net.name]) if drivers[net.name] else None
            out.append((p.name, pin, net.name, PHASES[arrives]["key"] if arrives is not None else None))
    return out


def straps(L, sim):
    """Per phase: straps to add and straps to remove.  A strap is added the
    phase an input is fitted without its driver and removed the phase the
    driver arrives.  {phase: {"add": [...], "remove": [...]}}"""
    out = {p["key"]: dict(add=[], remove=[]) for p in PHASES}
    seen = {}
    for p in PHASES:
        for part, pin, net, arrives in floating_inputs(L, sim, p["key"]):
            key = (part, pin)
            if key in seen:
                continue
            level, why = SPEC_STRAPS.get(net, (GND, "unused CMOS input: hold it at a defined level"))
            hole = L.pin_hole.get((part, pin))
            rec = dict(part=part, pin=pin, net=net, hole=hole, level=level, why=why, arrives=arrives)
            seen[key] = rec
            out[p["key"]]["add"].append(rec)
            if arrives is not None:
                out[arrives]["remove"].append(rec)
    return out


# ---------------------------------------------------------------------------
# helpers for the document
# ---------------------------------------------------------------------------

def strip_text(L, hole):
    """Human description of the 5-hole strip a pin sits on, e.g. 'BB3 a7–d7'."""
    b, c, r = hole
    cols = LY.COLS_L if c in LY.COLS_L else LY.COLS_R
    free = [x for x in cols if (b, x, r) not in L.used]
    return f"{b} {free[0]}{r}–{free[-1]}{r}" if free else f"{b} row {r} (strip full)"


def nearest_rail(hole, level):
    b, c, r = hole
    side = LY.side_of(c)
    return f"{b}:{side}{'+' if level == VCC else '-'}@{r}"


def wire_stats(wires):
    n_vcc = sum(1 for w in wires if w[2] == VCC)
    n_gnd = sum(1 for w in wires if w[2] == GND)
    total = sum(wire_mm(w[0], w[1]) for w in wires)
    bins = Counter()
    for h1, h2, _ in wires:
        mm = wire_mm(h1, h2)
        bins["≤50" if mm <= 50 else "51–100" if mm <= 100 else "101–150" if mm <= 150
             else "151–250" if mm <= 250 else ">250"] += 1
    order = ["≤50", "51–100", "101–150", "151–250", ">250"]
    return dict(n=len(wires), red=n_vcc, black=n_gnd, signal=len(wires) - n_vcc - n_gnd,
                total_m=total / 1000, bins=[(k, bins[k]) for k in order if bins[k]])


def cut_list(L, step_mm=10):
    """[(bin_low_mm, bin_high_mm, red, black, signal)] over every wire."""
    rows = defaultdict(lambda: [0, 0, 0])
    for h1, h2, net in L.wires:
        mm = wire_mm(h1, h2)
        lo = int((mm - 1) // step_mm) * step_mm
        rows[lo][0 if net == VCC else 1 if net == GND else 2] += 1
    return [(lo, lo + step_mm, *rows[lo]) for lo in sorted(rows)]


def _sub_holes(L, text):
    return re.sub(r"\{(U\d+)\.(\d+)\}", lambda m: fmt(L.pin_hole[(m.group(1), int(m.group(2)))]), text)


def dip_table():
    from .firmware import SCENARIOS
    rows = []
    for name, n in sorted(SCENARIOS.items(), key=lambda kv: kv[1]):
        closed = [f"SW{i}" for i in range(8) if (n >> i) & 1]
        rows.append((n, name, ", ".join(closed) if closed else "none (all open)"))
    return rows


def eeprom_delta(L):
    """Wires that change when U3 is a 28C256 EEPROM (pin 1 = A14, pin 27 = /WE
    tied high) instead of the AT27C256R (pin 1 = VPP tied high, pin 27 = A14).
    Returns (remove, add, eeprom_layout)."""
    E = LY.generate(mutations=["rom28c256"])

    def keyed(lay):      # identify a wire by the two strips it joins, so rail holes are interchangeable
        d = {}
        for a, b, n in lay.wires:
            d[(n,) + tuple(sorted((strip_key(a), strip_key(b)), key=str))] = (fmt(a), fmt(b), n)
        return d

    base, alt = keyed(L), keyed(E)
    key = lambda t: (t[2], t[0])
    return (sorted((base[k] for k in base.keys() - alt.keys()), key=key),
            sorted((alt[k] for k in alt.keys() - base.keys()), key=key), E)


# ---------------------------------------------------------------------------
# BOM
# ---------------------------------------------------------------------------

# Distributor search strings.  Only the WDC number was checked on a live
# product page (27 Oct 2026); the others follow Mouser's maker-prefix
# convention (595 TI, 579 Microchip, 913 Alliance, 604 Kingbright, 511 ST)
# and must be confirmed on the live page before ordering.
SOURCING = {
    "W65C02S6TPG-14": ("955-W65C02S6TPG-14", "verified"),
    "AS6C62256-55PCN": ("913-AS6C62256-55PCN", "pattern"),
    "AT27C256R-45PU": ("579-AT27C256R-45PU", "pattern"),
    "AT28C256-15PU": ("579-AT28C256-15PU", "pattern"),
    "MCP130-460DI/TO": ("579-MCP130-460DI/TO", "pattern"),
    "L7805ACV": ("511-L7805ACV", "pattern"),
    "SC56-11EWA": ("604-SC56-11EWA", "pattern; also DigiKey 2163728"),
}
for _mpn in ["SN74HCT541N", "SN74HC14N", "SN74HCT74N", "SN74AC14N", "SN74HCT04N", "CD74HC30E",
             "SN74HCT00N", "SN74HCT08N", "SN74HCT32N", "SN74HCT138N", "SN74HCT273N", "CD74HC10E",
             "SN74HCT244N", "SN74HC595N", "CD74HCT157E", "SN74HCT573N"]:
    SOURCING[_mpn] = (f"595-{_mpn}", "pattern")

# what a builder who has done a Ben Eater style 8-bit/6502 breadboard build tends to own already
HOBBY_STOCK = {"breadboard", "hookup wire", "100 nF", "10 µF", "220 Ω", "1 kΩ", "10 kΩ", "LED",
               "pushbutton", "DIP switch", "1N4148", "W65C02S", "AS6C62256", "AT28C256"}

_DESC = {
    ("R", "10k"): "10 kΩ resistor, ≥1/8 W", ("R", "4.7k"): "4.7 kΩ resistor, ≥1/8 W",
    ("R", "3.3k"): "3.3 kΩ resistor, 5 % or better, ≥1/8 W", ("R", "220"): "220 Ω resistor, ≥1/8 W",
    ("R", "1k"): "1 kΩ resistor, ≥1/8 W", ("R", "1k 1/4W"): "1 kΩ resistor, 1/4 W (rail bleeder)",
    ("R", "100k"): "100 kΩ resistor, ≥1/8 W",
    ("C", "100n"): "100 nF ceramic, ≥16 V, short leads", ("C", "10uF"): "10 µF electrolytic, ≥10 V",
    ("C", "560p C0G"): "560 pF C0G/NP0, ≥16 V (oscillator)", ("C", "1uF"): "1 µF, ≥10 V (reset RC)",
    ("C", "330n"): "330 nF, ≥25 V (regulator input)", ("C", "100uF"): "100 µF electrolytic, ≥25 V",
    ("C", "47uF"): "47 µF electrolytic, ≥10 V",
    ("D", "1N4148 (anode, cathode)"): "1N4148 signal diode", ("D", "1N5819 (anode, cathode)"): "1N5819 Schottky diode",
    ("S", "pushbutton"): "Normally-open momentary pushbutton", ("S", "DIP switch pole"): "Eight-pole SPST DIP switch",
    ("LED", "3 mm"): "3 mm LED (1 red FAULT, 2 yellow MESSAGE_LOCK / RESULT_LOCK)",
    ("DIGIT", "SC56-11EWA"): "Kingbright SC56-11EWA common-cathode digit",
}

CONSTRUCTION = [       # Section 2.2 items that are not netlist parts
    (10, "830-tie, 63-row solderless breadboard (BB1–BB10); buy at least one spare", "breadboard"),
    (1, "Passive perfboard about 250 × 30–50 mm for the LED panel", ""),
    (1, "Small perfboard plus screw terminals for the fused battery/regulator fixture", ""),
    (1, "TO-220 heatsink ≤15 °C/W with hardware", ""),
    (1, "500 mA fuse and holder", ""),
    (1, "SPST power switch ≥1 A at 15 V DC", ""),
    (1, "Eight-AA holder plus eight alkaline AA cells", ""),
    (1, "22 AWG solid hookup wire, several colours (red and black for power); about {wire_m:.0f} m in total", "hookup wire"),
]


def ic_rows():
    """Section 2.1 IC table: [(refs, qty, maker, mpn, package, function)]."""
    text = spec_text()
    sec = text[text.index("### 2.1"):text.index("### 2.2")]
    rows = []
    for refs, qty, part, pkg, fn in re.findall(r"^\| (U[^|]+) \| (\d+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|", sec, re.M):
        maker, rest = part.strip().split(" ", 1)
        mpn = rest.split(" / ")[0].strip().strip("*")
        rows.append((refs.strip(), int(qty), maker, mpn, pkg.strip(), fn.strip()))
    return rows


def bom(L):
    """Orderable BOM: ICs from spec Section 2.1 with sourcing, discrete parts
    counted from the layout, construction items from Section 2.2."""
    rows = []
    for refs, qty, maker, mpn, pkg, fn in ic_rows():
        src, status = SOURCING.get(mpn, ("", ""))
        hobby = any(k in mpn for k in HOBBY_STOCK)
        rows.append(dict(group="IC", refs=refs, qty=qty, item=f"{maker} {mpn}", detail=f"{pkg}; {fn}",
                         source=src, status=status, hobby=hobby, mpn=mpn, order=qty + SPARES(mpn, qty),
                         vendor="Mouser / DigiKey"))
    counts = Counter()
    for it in L.items:
        if it["kind"] == "U":
            continue
        counts[(it["kind"], it["value"])] += 1
    for (kind, value), n in sorted(counts.items(), key=lambda kv: (kv[0][0], -kv[1])):
        desc = _DESC.get((kind, value), f"{kind} {value}")
        qty = 1 if value == "DIP switch pole" else n
        hobby = any(k in desc for k in HOBBY_STOCK)
        src, status = SOURCING.get(value, ("", ""))
        digit = value == "SC56-11EWA"
        rows.append(dict(group="discrete", refs="", qty=qty, item=desc,
                         detail=f"{n} poles" if value == "DIP switch pole" else "",
                         source=src, status=status, hobby=hobby, mpn=value if digit else "",
                         order=qty + (2 if digit else 0), vendor="Mouser / DigiKey" if digit else "Amazon"))
    wire_m = sum(wire_mm(a, b) for a, b, _ in L.wires) / 1000 * 1.3
    for qty, desc, key in CONSTRUCTION:
        rows.append(dict(group="construction", refs="", qty=qty, item=desc.format(wire_m=wire_m),
                         detail="", source="", status="", hobby=key in HOBBY_STOCK, mpn="", order=qty,
                         vendor="Amazon"))
    src, status = SOURCING["AT28C256-15PU"]
    rows.append(dict(group="development", refs="U3 (dev)", qty=1, item="Microchip AT28C256-15PU",
                     detail="PDIP-28 EEPROM; reusable development ROM, see BUILD.md", source=src,
                     status=status, hobby=True, mpn="AT28C256-15PU", order=1, vendor="Mouser / DigiKey"))
    return rows


def SPARES(mpn, qty):
    """Spares to order on top of the installed count (spec Section 2: 'buy modest spares';
    three OTP blanks)."""
    if mpn.startswith("AT27C256R"):
        return 2                      # three blanks in total
    if mpn.startswith("SN74HC595"):
        return 2
    if mpn.startswith(("W65C02S", "L7805", "MCP130")):
        return 0
    if mpn.startswith("AS6C62256"):
        return 1
    return 1


# Amazon-side shopping list: (quantity, search term, what to check in the listing).
AMAZON_LIST = [
    ("11", "BusBoard BB830 breadboard (or a 10-pack of 830-tie boards)",
     "830 tie points, 63 rows, 0.6-inch gap between the two halves so the CPU and memories fit in c/g. "
     "The layout already includes rail bridge wires, so split or continuous power rails both work. "
     "Avoid the cheapest clones: loose rail contacts cause intermittent resets."),
    ("2 kits", "Elenco 140-piece pre-formed jumper wire kit",
     "22 AWG solid, 14 lengths up to 5 in; two kits cover the ~460 wires under 130 mm."),
    ("1 set", "22 AWG solid core hookup wire, 6 colours, spools",
     "Solid, not stranded. Red and black for power plus four signal colours; about 25 m per colour covers the "
     "~200 longer runs with slack."),
    ("2 packs of 100", "3.3k ohm 1/4 W resistors, pack of 100", "128 installed. 5 % carbon film or 1 % metal film, both fine."),
    ("1 pack of 100 each", "10k ohm and 220 ohm 1/4 W resistors, pack of 100",
     "27 and 20 installed; assortment kits rarely hold enough of one value."),
    ("1 kit", "1/4 W resistor assortment kit (metal film)",
     "Must include 4.7k (12 needed), 1k (8) and 100k (1)."),
    ("1 pack of 100", "0.1uF 50V ceramic capacitors (marked 104)", "50 installed. Short leads, through-hole."),
    ("1 pack of 20", "10uF 25V electrolytic capacitors", "10 installed, one per board."),
    ("1 kit", "Electrolytic capacitor assortment", "Needs 1uF, 47uF and 100uF; 25 V rating for the 100uF."),
    ("1 kit", "Ceramic disc capacitor assortment (C0G/NP0)",
     "Must contain 560 pF (561), 680 pF (681) or 1 nF (102) for the oscillator, and 330 nF (334) or buy "
     "a 0.33uF film capacitor separately."),
    ("1 pack", "1N4148 diodes, pack of 100", "One installed."),
    ("1 pack", "1N5819 Schottky diodes, pack of 20", "One installed, battery reverse protection."),
    ("1 pack each", "3mm red LEDs; 3mm yellow LEDs", "One red (FAULT) and two yellow (locks)."),
    ("1 pack", "6x6mm tactile pushbuttons, 4-pin, breadboard friendly, pack of 50", "6 installed."),
    ("1 pack", "8-position DIP switch, 2.54 mm pitch", "One installed; the pack gives spares."),
    ("1", "TO-220 heatsink with clip", "Under 15 C/W; the L7805ACV is already in the Mouser cart."),
    ("1 each", "Panel-mount 5x20mm fuse holder; 500mA 5x20mm fuses; SPST toggle switch; 8xAA battery holder with leads",
     "Battery fixture (spec Section 5.1); can wait until the board runs on the bench supply."),
    ("1", "12x18 cm double-sided prototype PCB, 2.54 mm",
     "LED panel as two rows of eight digits (spec Section 2.2 allows this): each row needs 48 columns "
     "(122 mm) for the digits plus room above for the 64 segment resistors mounted upright. A single row of "
     "all 16 digits needs 244 mm, which only a 20x30 cm board cut down to about 25x5 cm gives."),
    ("1", "5x7 cm double-sided prototype PCB, 2.54 mm", "Power fixture: regulator, supervisor, capacitors, bleeder, "
     "diode and screw terminals. Usually sold in multi-size packs that include the 12x18 cm board."),
    ("1 pack", "5.08 mm 2-pin screw terminal blocks", "Battery and regulator fixture connections."),
    ("1", "XGecu TL866II Plus or T48 programmer",
     "Either programs both ROM types (AT27C256R and AT28C256 are in the device list). XGecu's Xgpro software "
     "is Windows-only; the open-source minipro tool covers both models on macOS and Linux."),
]

# Bench tools the spec assumes (Section 2.2), separate from the parts order.
TOOLS_LIST = [
    ("5 V bench power supply with adjustable current limit",
     "Phases 1 to 7; a plain 5 V adapter works for the first boards but cannot limit a wiring mistake."),
    ("8-channel USB logic analyzer (24 MHz class)",
     "Decodes the address and data buses at the 13 to 88 kHz CPU clock; enough to see the reset vector fetch."),
    ("Oscilloscope, 100 MHz class, with a probe ground spring",
     "Required for the 5 ns PHI2 edge and the Section 11.2 handoff checks; a logic analyzer cannot substitute."),
]


# ---------------------------------------------------------------------------
# documents
# ---------------------------------------------------------------------------

def write_docs(L, outdir):
    os.makedirs(outdir, exist_ok=True)
    terms, kinds, sim = LY.schematic()
    phases, unassigned = plan(L)
    st = straps(L, sim)
    rem, add, E = eeprom_delta(L)
    from . import specdoc
    diag_hash = specdoc.sha256(specdoc.diagnostic_rom())

    out = []
    a = out.append
    a("# DTS-02 build sequence (generated)\n")
    a("Generated by `python3 -m sim wiring` from `spec.md` and the layout in `WIRING.md`. Do not edit by "
      "hand. This file orders the same ICs, parts and wires as `WIRING.md` into the bring-up phases of "
      "spec Section 11.1, so each phase can be built, powered and measured before the next one is added. "
      "Hole names follow the `WIRING.md` conventions.\n")
    n_ics = sum(len(p['ics']) for p in phases.values())
    n_parts = sum(len(p['parts']) for p in phases.values())
    n_wires = sum(len(p['wires']) for p in phases.values())
    a("## Checks on this sequence\n")
    a(f"- Every IC ({n_ics}), part ({n_parts}) and wire ({n_wires}) of `WIRING.md` appears in exactly one phase; "
      f"unassigned wires: {len(unassigned)}.")
    a("- A wire is listed only once both of its end strips exist (an IC pin, a part lead, a rail, or a landing "
      "strip already reached by an earlier wire).")
    a("- For each phase the netlist is scanned for inputs whose driver is not fitted yet. They are listed as "
      "straps to add, and again as straps to remove in the phase that fits the driver. After the last phase "
      "none remain, which matches the ERC of `python3 -m sim check`.")
    a("- The 28C256 development-ROM variant below is a separate generated layout; it passes the same "
      "connectivity check and runs the diagnostic ROM in simulation (`tests/test_buildplan.py`).\n")

    a("## Phase overview\n")
    a("| Phase | Spec | ICs | Parts | Wires | Wire (m) | Straps add / remove |")
    a("|---|---|---:|---:|---:|---:|---|")
    for p in PHASES:
        ph = phases[p["key"]]
        ws = wire_stats(ph["wires"])
        a(f"| {p['title']} | {p['step']} | {len(ph['ics'])} | {len(ph['parts'])} | {ws['n']} | "
          f"{ws['total_m']:.1f} | {len(st[p['key']]['add'])} / {len(st[p['key']]['remove'])} |")
    a("")

    a("## Test ROM scenarios by DIP switch\n")
    a("The boot/test ROM (`_build/rom/dts02_test.bin`) reads the DIP byte once after a fresh start, inverted "
      "so a closed pole is a 1 bit. SW0 is bit 0 (U14 pin 2).\n")
    a("| Byte | Scenario | Poles closed |")
    a("|---:|---|---|")
    for n, name, closed in dip_table():
        a(f"| {n} | `{name}` | {closed} |")
    a("")

    for p in PHASES:
        key = p["key"]
        ph = phases[key]
        a(f"## Phase {PHASE_INDEX[key] + 1}: {p['title']}\n")
        a(f"*{p['step']}.* {p['goal']}\n")
        if p.get("note"):
            a(f"> {p['note']}\n")
        if ph["ics"]:
            a("**Seat** (notch toward row 1): " + ", ".join(
                f"{u} pin 1 at {fmt(L.pin_hole[(u, 1)])}" for u in ph["ics"]) + "\n")
        if ph["parts"]:
            a("**Place**\n")
            a("| Part | Value | Leads |")
            a("|---|---|---|")
            for it in sorted(ph["parts"], key=lambda it: it["ref"]):
                a(f"| {it['ref']} | {it['value']} | " + ", ".join(f"{fmt(h)} ({n})" for h, n in it["leads"]) + " |")
            a("")
        if ph["wires"]:
            ws = wire_stats(ph["wires"])
            a(f"**Wire** — {ws['n']} wires ({ws['red']} red +5 V, {ws['black']} black GND, {ws['signal']} signal), "
              f"about {ws['total_m']:.1f} m; lengths " + ", ".join(f"{k} mm ×{n}" for k, n in ws["bins"]) + "\n")
            a("| Net | From | To | mm |")
            a("|---|---|---|---:|")
            for h1, h2, net in sorted(ph["wires"], key=lambda w: (_bkey(w[0][0]), _bkey(w[1][0]), w[2], fmt(w[0]))):
                a(f"| {net} | {fmt(h1)} | {fmt(h2)} | {wire_mm(h1, h2):.0f} |")
            a("")
        if st[key]["remove"]:
            a("**Remove straps** (their drivers are fitted in this phase)\n")
            a("| IC pin | Net | Strap was |")
            a("|---|---|---|")
            for r in st[key]["remove"]:
                a(f"| {r['part']} pin {r['pin']} ({fmt(r['hole'])}) | {r['net']} | {r['level']} |")
            a("")
        if st[key]["add"]:
            a("**Add straps** — inputs fitted now whose driver comes later\n")
            a("| IC pin | Net | Tie to | Jumper | Remove in | Why |")
            a("|---|---|---|---|---|---|")
            for r in st[key]["add"]:
                when = f"phase {PHASE_INDEX[r['arrives']] + 1}" if r["arrives"] else "never"
                a(f"| {r['part']} pin {r['pin']} ({fmt(r['hole'])}) | {r['net']} | {r['level']} | "
                  f"{strip_text(L, r['hole'])} → {nearest_rail(r['hole'], r['level'])} | {when} | {r['why']} |")
            a("")
        a("**Check before the next phase**\n")
        for c in p["checks"]:
            a(f"- {_sub_holes(L, c)}")
        a("")

    a("## Development ROM: 28C256 EEPROM in the U3 socket\n")
    a("The AT27C256R is one-time programmable, so every firmware iteration costs a chip. An AT28C256 EEPROM "
      "(pin-compatible with the AS6C62256 SRAM) fits the same socket with two pin changes: pin 1 becomes A14 "
      "instead of VPP, and pin 27 becomes /WE, held at +5 V, instead of A14. Its 150 ns access is far inside "
      "the read window at any legal clock. Program it with the same images; the TL866II Plus device list "
      "includes both AT27C256R and AT28C256. Return to the OTP part and the `WIRING.md` wiring for the "
      "qualified build. Wiring delta, generated from a second layout with U3 as a 28C256:\n")
    a("Remove:\n")
    a("| Net | From | To |")
    a("|---|---|---|")
    for f, t, n in rem:
        a(f"| {n} | {f} | {t} |")
    a("\nAdd:\n")
    a("| Net | From | To |")
    a("|---|---|---|")
    for f, t, n in add:
        a(f"| {n} | {f} | {t} |")
    a("")

    a("## Single-stepping the bus\n")
    clk_wires = [w for w in L.wires if w[2] == "MASTER_CLK"
                 and strip_key(L.pin_hole[("U5", 2)]) in (strip_key(w[0]), strip_key(w[1]))]
    if clk_wires:
        w = clk_wires[0]
        u5_end, far_end = (w[0], w[1]) if strip_key(w[0]) == strip_key(L.pin_hole[("U5", 2)]) else (w[1], w[0])
        a(f"MASTER_CLK leaves the oscillator on the jumper {fmt(u5_end)} → {fmt(far_end)}. To drive the board "
          f"from a debounced manual or slow external clock, lift the {fmt(u5_end)} end and feed the clock into "
          f"the {fmt(far_end)} strip instead; the oscillator keeps running into nothing. Six master pulses make "
          f"one CPU cycle, and the W65C02S is fully static, so the bus can be held and read at leisure. A bus "
          f"monitor on A0–A15 (U1 pins 9–25) and C_D0–C_D7 (U1 pins 33–26) should sample on the falling edge of "
          f"PHI2 at {fmt(L.pin_hole[('U1', 37)])}, where both read and write data are valid.\n")

    a("## Cut list (every wire)\n")
    a("Estimated bare lengths, 10 mm bins. Pre-cut jumper kits typically stop at 127 mm (5 in); longer wires come "
      "off the roll.\n")
    a("| mm | Red (+5 V) | Black (GND) | Signal | Total |")
    a("|---|---:|---:|---:|---:|")
    for lo, hi, r, b, s in cut_list(L):
        a(f"| {lo + 1}–{hi} | {r} | {b} | {s} | {r + b + s} |")
    a("")
    path = os.path.join(outdir, "BUILD.md")
    with open(path, "w") as f:
        f.write("\n".join(out) + "\n")
    return path


def _bkey(b):
    order = LY.BOARDS + LY.PANELS
    return order.index(b) if b in order else 99


def write_bom(L, outdir):
    os.makedirs(outdir, exist_ok=True)
    rows = bom(L)
    with open(os.path.join(outdir, "bom.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["group", "refs", "qty_installed", "qty_to_order", "item", "detail", "vendor",
                    "distributor_search", "source_status", "common_hobby_stock"])
        for r in rows:
            w.writerow([r["group"], r["refs"], r["qty"], r["order"], r["item"], r["detail"], r["vendor"],
                        r["source"], r["status"], "yes" if r["hobby"] else ""])
    mouser = []                      # one line per manufacturer part number, spares counted once
    for r in rows:
        if not (r["mpn"] and r["vendor"].startswith("Mouser")):
            continue
        prev = next((m for m in mouser if m["mpn"] == r["mpn"]), None)
        if prev:
            prev["qty"] += r["qty"]
            prev["refs"] = f"{prev['refs']}, {r['refs']}"
            prev["order"] = prev["qty"] + SPARES(r["mpn"], prev["qty"])
        else:
            mouser.append(dict(r))
    with open(os.path.join(outdir, "order_mouser.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Manufacturer Part Number", "Quantity", "Description"])
        for r in mouser:
            w.writerow([r["mpn"], r["order"], r["item"] + (f" ({r['refs']})" if r["refs"] else "")])
    out = []
    a = out.append
    a("# DTS-02 bill of materials (generated)\n")
    a("## How to order\n")
    a("1. **Semiconductors and digits: one distributor cart.** Upload `order_mouser.csv` (manufacturer part "
      "number, quantity with spares) to Mouser's BOM tool, or paste the numbers into DigiKey; both carry "
      "every line. Amazon listings for these parts are resellers at a markup or unverifiable pulls, and the "
      "exact TI family (HC, HCT, AC) matters here. Cheaper option with slower shipping: Tayda Electronics "
      "stocks most 74HC/HCT DIPs for a fraction of the price; check each part number.")
    a("2. **Everything else: Amazon** (or any hobby supplier). The list below has the quantities with spares. "
      "Generic 0.56-inch common-cathode red digits (the `5161AS` type) share the SC56-11EWA pinout and are an "
      "acceptable fallback if the Kingbright part is back-ordered; phase 6 of `BUILD.md` checks one digit "
      "before the panel is soldered either way.")
    a("3. **Order the memories and digits first**; they have shown the longest lead times.\n")
    a("### Amazon list\n")
    a("| Qty | Search for | What to check |")
    a("|---|---|---|")
    for q, d, chk in AMAZON_LIST:
        a(f"| {q} | {d} | {chk} |")
    a("")
    a("### Bench tools (not parts)\n")
    a("| Tool | Why |")
    a("|---|---|")
    for t, why in TOOLS_LIST:
        a(f"| {t} | {why} |")
    a("")
    a("### Distributor cart (`order_mouser.csv`)\n")
    a("| Order qty | Installed | Manufacturer part | For |")
    a("|---:|---:|---|---|")
    for r in mouser:
        a(f"| {r['order']} | {r['qty']} | {r['mpn']} | {r['refs'] or r['item']} |")
    a("")
    a("Generated by `python3 -m sim wiring`. IC lines come from spec Section 2.1; discrete quantities are "
      "counted from the layout in `WIRING.md` (which `python3 -m sim check` reconciles with Section 2.2); "
      "construction items are Section 2.2. `bom.csv` is the same list for a spreadsheet.\n")
    a("The *Distributor search* column is a Mouser part-number pattern, not a stock claim: only the WDC CPU "
      "number was confirmed on a live product page; the rest follow Mouser's maker prefixes and must be "
      "checked before ordering. DigiKey carries the Kingbright digit. Do not substitute 74LS or a surface-mount "
      "suffix; the timing review assumes the listed families (Section 2.1).\n")
    a("*Hobby stock* marks items a builder with a Ben Eater style 8-bit or 6502 breadboard kit usually has "
      "already; check quantities, because this design uses far more of some values.\n")
    for group, title in [("IC", "Integrated circuits"), ("discrete", "Discrete parts"),
                         ("construction", "Construction"), ("development", "Development only")]:
        a(f"## {title}\n")
        a("| Qty | Item | Detail | Refs | Vendor | Distributor search | Hobby stock |")
        a("|---:|---|---|---|---|---|---|")
        for r in rows:
            if r["group"] != group:
                continue
            src = r["source"] + (f" ({r['status']})" if r["status"] and r["status"] != "pattern" else "")
            a(f"| {r['qty']} | {r['item']} | {r['detail']} | {r['refs']} | {r['vendor']} | {src} | "
              f"{'yes' if r['hobby'] else ''} |")
        a("")
    path = os.path.join(outdir, "BOM.md")
    with open(path, "w") as f:
        f.write("\n".join(out) + "\n")
    return path
