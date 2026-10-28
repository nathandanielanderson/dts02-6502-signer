"""Command line: python3 -m sim <command> [options]

  check                 static + analog checks (fast)
  run SCENARIO          boot the test ROM in a scenario and report the board state
  diag                  run the spec's Section 11.3 diagnostic ROM
  handoff               Section 11.2 bus-handoff measurements
  race                  worst-case read-window corner, rev 0.3 vs rev 0.4
  sign                  sign a Solana transfer with the 6502 firmware (fast emulator)
                        and check it against Python RFC 8032 and OpenSSL
  wiring                generate the hole-level breadboard layout + jumper list
                        (wiring/WIRING.md, wiring/wiring.csv), the phase-ordered
                        build sequence (wiring/BUILD.md) and the orderable BOM
                        (wiring/BOM.md, wiring/bom.csv), and check them
  rom                   write the ROM images for the programmer (_build/rom/):
                        diagnostic, boot/test and reference signer, with SHA-256
"""

import argparse
import collections
import sys

from . import analog, checks, corners, specdoc
from .board import P_D
from .firmware import SCENARIOS


def _bench_kw(a):
    kw = dict(seed=a.seed, master_hz=a.freq * 1e3)
    if a.rev03:
        kw["mutations"] = ["rev03"]
    if a.vcd:
        from .vcd import VCD
        kw["vcd"] = VCD(a.vcd)
    return kw


def _summary(b):
    c = collections.Counter(v.kind for v in b.violations())
    print(f"  cycles simulated : {len(b.cpu.cycles)}  ({b.sim.now/1e6:.2f} ms)")
    print(f"  FAULT/RESULT/MSG : {b.net('FAULT')}/{b.net('RESULT_LOCK')}/{b.net('MESSAGE_LOCK')}")
    print(f"  display          : [{b.display_text()}]")
    print(f"  A X Y S PC       : {b.cpu.core.a:02X} {b.cpu.core.x:02X} {b.cpu.core.y:02X} "
          f"{b.cpu.core.s:02X} {b.cpu.core.pc:04X}")
    print(f"  violations       : {sum(c.values())} {dict(c) if c else ''}")
    for v in b.violations()[:10]:
        print("   ", v)


def cmd_check(a):
    ok = True
    rom = specdoc.diagnostic_rom()
    good = specdoc.sha256(rom) == specdoc.expected_diagnostic_hash()
    ok &= good
    print(f"diagnostic ROM SHA-256 matches spec: {good}")
    from . import ed25519_ref as E
    import re
    t = specdoc.spec_text()
    sec = t[t.index("### 10.6"):t.index("## 11.")]
    v = {k: bytes.fromhex(h) for k, h in re.findall(r"^(seed|A|R|S)\s*=\s*([0-9a-f]+)", sec, re.M)}
    good = E.public_key(v["seed"]) == v["A"] and E.sign(v["seed"], b"") == v["R"] + v["S"]
    ok &= good
    print(f"RFC 8032 vector reproduces (independent implementation): {good}")
    rows, probs = checks.placement()
    ok &= not probs
    print(f"placement table: {len(rows)} ICs, problems: {probs or 'none'}")
    from .runner import Bench
    b = Bench(scenario="idle")
    errs, notes = checks.erc(b.sim)
    ok &= not errs
    print(f"ERC: {len(errs)} errors, {len(notes)} notes")
    for e in errs + notes:
        print("   ", e)
    bad = [(i, s, n) for i, s, n in checks.bom(b.sim) if s != n]
    ok &= not bad
    print(f"BOM vs netlist: {'all match' if not bad else bad}")
    print("\nanalog:")
    print("  " + analog.report().replace("\n", "\n  "))
    return 0 if ok else 1


def cmd_run(a):
    from .runner import Bench
    b = Bench(scenario=a.scenario, **_bench_kw(a))
    label = "done"
    b.run_to(label)
    print(f"scenario {a.scenario}: reached '{label}'")
    _summary(b)
    if a.reset:
        b.press_reset()
        st = (b.net("FAULT"), b.net("RESULT_LOCK"), b.net("MESSAGE_LOCK"))
        target = "hold" if st[0] == 1 else ("idle" if st != (0, 0, 0) else "done")
        b.run_to(target, max_cycles=60_000)
        b.run_cycles(20)
        print(f"after CPU RESET: reached '{target}'")
        _summary(b)
    if a.vcd:
        b.sim.vcd.close()
        print(f"waveform written to {a.vcd}")
    return 1 if b.violations() else 0


def cmd_diag(a):
    from .runner import Bench
    b = Bench(image=specdoc.diagnostic_rom(), symbols={"loop": 0x800A}, **_bench_kw(a))
    b.h.set_switch_byte(a.switch)
    b.run_to("loop")
    b.run_cycles(a.cycles)
    print(f"diagnostic ROM, raw switch byte ${a.switch:02X}: RAM[$0200]=${b.ram.mem[0x200]:02X}")
    _summary(b)
    if a.vcd:
        b.sim.vcd.close()
        print(f"waveform written to {a.vcd}")
    return 0 if b.ram.mem[0x200] == a.switch and not b.violations() else 1


def cmd_handoff(a):
    from .handoff import measure
    kw = _bench_kw(a)
    r = measure(kw, scenario="ram")
    for k, v in r.items():
        if k != "violations":
            print(f"  {k:38s} {v}")
    print(f"  violations                             {len(r['violations'])}")
    return 0


def cmd_race(a):
    from .runner import Bench
    for label, mut, corner in [("rev 0.3", ["rev03"], corners.read_window_trailing_edge),
                               ("rev 0.4", [], corners.read_window_six_state_fix)]:
        b = Bench(image=specdoc.diagnostic_rom(), symbols={"loop": 0x800A}, seed=a.seed,
                  mutations=mut)
        corner(b)
        b.sim.driver_watch.update(P_D)
        b.run_cycles(150)
        ov = [e - s for n in P_D for s, e, o in
              checks.driver_intervals(b.sim.driver_log.get(n, []), b.sim.check_from, b.sim.now)
              if len(o) > 1]
        print(f"{label:14s}: {len(ov)} P_D overlap intervals, longest {max(ov, default=0):.1f} ns")
    return 0


def cmd_wiring(a):
    from . import buildplan as BP, layout as LY
    L = LY.generate()
    path = LY.write_docs(L, a.out)
    remap, pull, con, cap = LY.physical_netlist(L)
    problems, targets, info, _ = LY.harness_checks(L)
    s = LY.summary(L)
    print(f"wrote {path} and wiring.csv")
    print(f"wrote {BP.write_docs(L, a.out)} and {BP.write_bom(L, a.out)} (+ bom.csv)")
    phases, unassigned = BP.plan(L)
    print("  phases: " + ", ".join(f"{p['key']} {len(phases[p['key']]['wires'])}w" for p in BP.PHASES)
          + f"; unassigned wires {len(unassigned)}")
    print(f"  {s['ics']} ICs, {s['parts']} parts, {s['wires']} wires ({s['inter_board_wires']} inter-board)")
    print(f"  layout errors {len(L.errors)}, shorts {len(con['shorts'])}, opens {len(con['opens'])}")
    print(f"  harness rules: {problems or 'pass'}")
    print(f"  length targets: {targets or 'met'}")
    for k, v in info.items():
        print(f"  {k}: {v if not isinstance(v, float) else round(v)}")
    return 1 if (L.errors or con["shorts"] or con["opens"] or problems or unassigned) else 0


def cmd_rom(a):
    import hashlib
    import os
    from . import firmware as FW, signer_fw as SF
    os.makedirs(a.out, exist_ok=True)
    diag = specdoc.diagnostic_rom()
    test_img, test_syms = FW.boot_rom(zero_end_page=0x40)
    sign_img, sign_syms, _ = SF.build()
    images = [
        ("dts02_diag.bin", diag, None,
         "spec Section 11.3 bus diagnostic; copies the raw DIP byte to $0200 forever"),
        ("dts02_test.bin", test_img, test_syms,
         "boot/test ROM: Section 10.1 state machine, scenario by DIP byte (wiring/BUILD.md)"),
        ("dts02_signer.bin", sign_img, sign_syms,
         "reference Ed25519 signer for the emulator; on hardware it rejects the empty envelope and halts"),
    ]
    ok = specdoc.sha256(diag) == specdoc.expected_diagnostic_hash()
    sums = []
    for name, img, syms, what in images:
        assert len(img) == 32768, name
        path = os.path.join(a.out, name)
        with open(path, "wb") as f:
            f.write(img)
        h = hashlib.sha256(img).hexdigest()
        sums.append(f"{h}  {name}")
        print(f"{name:18s} {len(img)} bytes  sha256 {h}")
        print(f"{'':18s} {what}")
        if syms:
            spath = path[:-4] + ".sym"
            with open(spath, "w") as f:
                for lab, addr in sorted(syms.items(), key=lambda kv: kv[1]):
                    f.write(f"{addr:04X} {lab}\n")
    with open(os.path.join(a.out, "SHA256SUMS"), "w") as f:
        f.write("\n".join(sums) + "\n")
    print(f"diagnostic image hash matches spec Section 11.3: {ok}")
    print(f"ROM offset = CPU address - $8000; program with VPP at the programmer, read back and compare "
          f"against SHA256SUMS in {a.out}/")
    return 0 if ok else 1


def cmd_sign(a):
    import base64
    import hashlib
    from . import ed25519_ref as E, signer_fw as F, solana as SOL
    from .signer_harness import Fw
    seed = hashlib.sha256(a.seed_text.encode()).digest()
    pk = E.public_key(seed)
    to = SOL.b58decode(a.to) if a.to else E.public_key(hashlib.sha256(b"recipient").digest())
    bh = SOL.b58decode(a.blockhash) if a.blockhash else hashlib.sha256(b"blockhash").digest()
    msg = SOL.transfer_message(pk, to, a.lamports, bh)
    fw = Fw(double_sign=not a.single, verify=not a.no_verify)
    fw.put(F.SEED, seed)
    fw.put(F.ENV, F.envelope(msg, pk))
    cycles = fw.call("sign_main")
    m = fw.m.m
    rec = fw.get(F.REC, 256)
    sig = rec[0x2C:0x6C]
    ok = (fw.get(F.ZP["STATUS"], 1)[0] == 0 and sig == E.sign(seed, msg)
          and sig == SOL.openssl_sign(seed, msg) and rec == F.expected_record(msg, pk, sig))
    print(f"signer   {SOL.b58encode(pk)}  (test seed from text {a.seed_text!r}; never fund it)")
    print(f"message  {len(msg)} bytes, transfer {a.lamports} lamports")
    print(f"status   {fw.get(F.ZP['STATUS'], 1)[0]:#04x}  MESSAGE_LOCK={m.msg_lock} RESULT_LOCK={m.res_lock} FAULT={m.fault}")
    print(f"sig      {SOL.b58encode(sig)}")
    print(f"matches  python RFC 8032 + OpenSSL + record format: {ok}")
    print(f"cycles   {cycles:,}  ->  {cycles / 88e3 / 3600:.1f} h at 88 kHz, "
          f"{cycles / 47e3 / 3600:.1f} h at 47 kHz, {cycles / 1e6 / 60:.0f} min at 1 MHz")
    print(f"tx       {base64.b64encode(SOL.transaction(sig, msg)).decode()}")
    return 0 if ok else 1


def main(argv=None):
    p = argparse.ArgumentParser(prog="python3 -m sim", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("check")
    sg = sub.add_parser("sign")
    sg.add_argument("--seed-text", default="DTS-02 public test fixture seed - never fund")
    sg.add_argument("--to", help="recipient (base58)")
    sg.add_argument("--blockhash", help="recent blockhash (base58)")
    sg.add_argument("--lamports", type=int, default=1_000_000)
    sg.add_argument("--single", action="store_true", help="skip the second signature")
    sg.add_argument("--no-verify", action="store_true", help="skip on-device verification")
    w = sub.add_parser("wiring")
    w.add_argument("--out", default="wiring")
    r = sub.add_parser("rom")
    r.add_argument("--out", default="_build/rom")
    for name in ("run", "diag", "handoff", "race"):
        s = sub.add_parser(name)
        if name == "run":
            s.add_argument("scenario", choices=sorted(SCENARIOS))
            s.add_argument("--reset", action="store_true", help="press CPU RESET afterwards")
        if name == "diag":
            s.add_argument("--switch", type=lambda x: int(x, 0), default=0xA5)
            s.add_argument("--cycles", type=int, default=200)
        s.add_argument("--freq", type=float, default=380, help="master clock, kHz")
        s.add_argument("--seed", type=int, default=1, help="delay Monte Carlo seed")
        s.add_argument("--rev03", action="store_true", help="simulate the revision 0.3 wiring instead")
        s.add_argument("--vcd", help="write a GTKWave VCD file")
    a = p.parse_args(argv)
    fn = {"check": cmd_check, "run": cmd_run, "diag": cmd_diag, "handoff": cmd_handoff,
          "race": cmd_race, "wiring": cmd_wiring, "sign": cmd_sign, "rom": cmd_rom}.get(a.cmd or "check")
    return fn(a)


if __name__ == "__main__":
    sys.exit(main())
