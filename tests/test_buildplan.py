"""Build sequence (wiring/BUILD.md), BOM, ROM images and the 28C256
development-ROM variant."""

import os
import tempfile
import unittest
from collections import Counter

from sim import buildplan as BP, checks, layout as LY, specdoc
from sim.runner import Bench

L = LY.generate()
TERMS, KINDS, SIM = LY.schematic()
PHASES, UNASSIGNED = BP.plan(L)
IDX = BP.PHASE_INDEX


class TestPhases(unittest.TestCase):
    def test_everything_assigned_exactly_once(self):
        self.assertEqual(UNASSIGNED, [])
        wires = Counter(w for p in PHASES.values() for w in p["wires"])
        self.assertEqual(sum(wires.values()), len(L.wires))
        self.assertEqual(max(wires.values()), 1)
        parts = [it["ref"] for p in PHASES.values() for it in p["parts"]]
        self.assertEqual(sorted(parts), sorted(it["ref"] for it in L.items))
        ics = [u for p in PHASES.values() for u in p["ics"]]
        self.assertEqual(sorted(ics), sorted({u for u, _ in L.pin_hole}))

    def test_no_wire_lands_on_a_component_fitted_later(self):
        comp_phase = {}
        for (u, pin), h in L.pin_hole.items():
            k = LY.strip_key(h)
            comp_phase[k] = min(comp_phase.get(k, 99), IDX[BP.IC_PHASE[u]])
        for it in L.items:
            for h, _ in it["leads"]:
                k = LY.strip_key(h)
                comp_phase[k] = min(comp_phase.get(k, 99), IDX[BP.part_phase(it["ref"])])
        for key, ph in PHASES.items():
            for h1, h2, net in ph["wires"]:
                for h in (h1, h2):
                    if h[1] in LY.RAILS:                 # rails exist from the power phase
                        continue
                    k = LY.strip_key(h)
                    if k in comp_phase:
                        self.assertLessEqual(comp_phase[k], IDX[key], (net, LY.fmt(h1), LY.fmt(h2), key))

    def test_every_ic_wire_present_by_its_phase(self):
        # each IC's supply pins are wired to the rails no later than the IC is seated
        for key, ph in PHASES.items():
            fitted = {u for k2, p2 in PHASES.items() if IDX[k2] <= IDX[key] for u in p2["ics"]}
            wired = {LY.strip_key(h) for k2, p2 in PHASES.items() if IDX[k2] <= IDX[key]
                     for w in p2["wires"] for h in w[:2]}
            for u in fitted:
                for pin, net in TERMS.items():
                    if pin[0] == u and net in ("VCC", "GND"):
                        self.assertIn(LY.strip_key(L.pin_hole[pin]), wired, (u, pin, key))

    def test_core_phase_fits_the_read_window_gate(self):
        # rev 0.4 moved RD_WIN_N to U18; the spec's step-3 text still lists only U8-U13
        self.assertIn("U18", PHASES["core"]["ics"])
        self.assertEqual(TERMS[("U18", 6)], "RD_WIN_N")
        self.assertEqual(TERMS[("U3", 22)], "RD_WIN_N")

    def test_straps_match_the_spec_and_clear_at_the_end(self):
        st = BP.straps(L, SIM)
        spec = {("U12", 13), ("U18", 13), ("U15", 7), ("U15", 8), ("U15", 9)}
        removed_in_locks = {(r["part"], r["pin"]) for r in st["locks"]["remove"]}
        self.assertEqual(removed_in_locks, spec)
        levels = {(r["part"], r["pin"]): r["level"] for k in st for r in st[k]["add"]}
        self.assertEqual(levels[("U18", 13)], "VCC")
        self.assertEqual(levels[("U12", 13)], "GND")
        added = Counter((r["part"], r["pin"]) for k in st for r in st[k]["add"])
        removed = Counter((r["part"], r["pin"]) for k in st for r in st[k]["remove"])
        self.assertEqual(added, removed)                 # every strap comes off again
        self.assertEqual(BP.floating_inputs(L, SIM, "locks"), [])

    def test_clock_phase_straps_are_the_core_inputs(self):
        st = BP.straps(L, SIM)
        self.assertEqual({(r["part"], r["pin"], r["arrives"]) for r in st["clock"]["add"]},
                         {("U11", 12, "core"), ("U11", 13, "core"), ("U45", 2, "core")})

    def test_dip_table_covers_every_scenario(self):
        from sim.firmware import SCENARIOS
        self.assertEqual({n for n, _, _ in BP.dip_table()}, set(SCENARIOS.values()))


class TestEepromVariant(unittest.TestCase):
    def test_delta_is_only_the_rom_pin_swap(self):
        rem, add, E = BP.eeprom_delta(L)
        self.assertLessEqual(len(rem), 4)
        self.assertLessEqual(len(add), 4)
        self.assertEqual({n for _, _, n in rem + add}, {"A14", "VCC"})
        remap = LY.physical_netlist(E)[0]
        self.assertEqual((remap[("U3", 1)], remap[("U3", 27)]), ("A14", "VCC"))

    def test_eeprom_layout_connects_and_runs_diagnostic(self):
        rem, add, E = BP.eeprom_delta(L)
        self.assertEqual(E.errors, [])
        remap, pull, con, cap = LY.physical_netlist(E)
        self.assertEqual((con["shorts"], con["opens"]), ([], []))
        b = Bench(image=specdoc.diagnostic_rom(), symbols={"loop": 0x800A}, seed=3,
                  physical=(remap, pull), mutations=["rom28c256"])
        b.h.set_switch_byte(0x5A)
        b.run_to("loop")
        b.run_cycles(60)
        self.assertEqual(b.ram.mem[0x200], 0x5A)
        self.assertEqual(b.violations(), [])
        self.assertEqual(checks.erc(b.sim)[0], [])


class TestRomImages(unittest.TestCase):
    def test_rom_command_writes_images_and_hashes(self):
        from sim.__main__ import main
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(main(["rom", "--out", d]), 0)
            names = sorted(os.listdir(d))
            self.assertEqual(names, ["SHA256SUMS", "dts02_diag.bin", "dts02_signer.bin",
                                     "dts02_signer.sym", "dts02_test.bin", "dts02_test.sym"])
            def read(n, mode="rb"):
                with open(os.path.join(d, n), mode) as f:
                    return f.read()
            self.assertEqual(specdoc.sha256(read("dts02_diag.bin")), specdoc.expected_diagnostic_hash())
            for n in ("dts02_test.bin", "dts02_signer.bin"):
                img = read(n)
                self.assertEqual(len(img), 32768)
                self.assertEqual(img[0x7FFC:0x7FFE], b"\x00\x80", n)     # reset vector $8000
            sums = read("SHA256SUMS", "r").splitlines()
            self.assertEqual(len(sums), 3)
            self.assertTrue(all(len(x.split()[0]) == 64 for x in sums))
            syms = dict(x.split()[::-1] for x in read("dts02_test.sym", "r").splitlines())
            self.assertEqual(syms["reset"], "8000")


class TestBom(unittest.TestCase):
    def test_bom_matches_spec_quantities(self):
        rows = BP.bom(L)
        ics = sum(r["qty"] for r in rows if r["group"] == "IC")
        self.assertEqual(ics, 45)
        by_item = {r["item"]: r["qty"] for r in rows if r["group"] == "discrete"}
        want = {
            "3.3 kΩ resistor, 5 % or better, ≥1/8 W": 128, "220 Ω resistor, ≥1/8 W": 20,
            "4.7 kΩ resistor, ≥1/8 W": 12, "10 kΩ resistor, ≥1/8 W": 27,
            "100 nF ceramic, ≥16 V, short leads": 50, "10 µF electrolytic, ≥10 V": 10,
            "560 pF C0G/NP0, ≥16 V (oscillator)": 1, "Kingbright SC56-11EWA common-cathode digit": 16,
            "Eight-pole SPST DIP switch": 1, "Normally-open momentary pushbutton": 6,
        }
        for k, v in want.items():
            self.assertEqual(by_item.get(k), v, k)
        # every spec IC line has a sourcing entry
        self.assertTrue(all(r["source"] for r in rows if r["group"] == "IC"))

    def test_oscillator_capacitor_is_the_rev04_value(self):
        c = [it for it in L.items if it["ref"] == "C_OSC"][0]
        self.assertTrue(c["value"].startswith("560p"))

    def test_documents_regenerate(self):
        with tempfile.TemporaryDirectory() as d:
            BP.write_docs(L, d)
            BP.write_bom(L, d)
            text = open(os.path.join(d, "BUILD.md")).read()
            self.assertIn("## Phase 8: Bank locks", text)
            self.assertIn("U18 pin 13 (BB4:f52) | FAULT_N | VCC", text)
            self.assertTrue(os.path.exists(os.path.join(d, "bom.csv")))


if __name__ == "__main__":
    unittest.main()
