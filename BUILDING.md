# Building DTS-02

This is the short path from the repository to a working breadboard. The design itself is `spec.md` (revision 0.4); everything below is generated from it or points into it. Build with public test keys only: this revision is a computer with experimental memory locks, not a custody device (spec Section 12).

## 1. Generate the build documents

```sh
python3 -m sim wiring     # wiring/WIRING.md, BUILD.md, BOM.md (+ csv)
python3 -m sim rom        # _build/rom/*.bin + SHA256SUMS for the programmer
python3 -m sim check      # confirms the documents still match the spec
```

| File | What it is for |
|---|---|
| `wiring/BOM.md`, `wiring/bom.csv` | Order list: 45 ICs, every discrete part counted from the netlist, construction items, distributor search strings. |
| `wiring/BUILD.md` | The spec's Section 11.1 bring-up sequence as eight checklists: what to seat, place and wire in each phase, which inputs to strap until their driver exists, what to measure before moving on. |
| `wiring/WIRING.md`, `wiring/wiring.csv` | The same 669 wires and 298 parts by board, hole by hole, for reference while debugging. |
| `_build/rom/dts02_diag.bin` | Spec Section 11.3 bus diagnostic (hash must match the spec). Phases 3–5. |
| `_build/rom/dts02_test.bin` | Boot/test ROM: RAM walk, lock and fault scenarios, font page, lamp test, selected by the DIP switches. Phases 5–8. |
| `_build/rom/dts02_signer.bin` | Reference Ed25519 signer. It has no seed entry or UI, so on hardware it rejects the empty envelope and halts; it exists for the emulator (`python3 -m sim sign`). |

## 2. Order

Start from `wiring/BOM.md`. Points that affect lead time:

- **Memories and digits first.** The W65C02S number is confirmed at Mouser; the AS6C62256 SRAM and the SC56-11EWA digit showed long factory lead times at some distributors when checked, so order those before anything else.
- **Logic families matter.** HCT where the spec says HCT, HC where it says HC, AC for U7. 74LS parts from an 8-bit kit are not substitutes (Section 2.1).
- **ROM strategy.** The AT27C256R is one-time programmable. For development, fit an AT28C256-15 EEPROM instead: same socket, two wires differ, listed at the end of `BUILD.md`. The XGecu TL866II Plus device list includes both parts. Keep the OTP part for the qualified build and buy the three blanks the spec asks for.
- **Quantities.** 128 segment resistors, 50 bypass capacitors, 16 shift registers, 10 breadboards and roughly 85 m of hookup wire. An 8-bit-computer parts box covers the values but rarely the counts.

## 3. Bench tools

- Current-limited 5 V bench supply for phases 1–7; the battery fixture can wait.
- DMM, and an oscilloscope fast enough to judge a 5 ns PHI2 edge and the Section 11.2 handoffs (a ground spring on the probe).
- Logic analyzer or an Arduino-style bus monitor on A0–A15 and C_D0–C_D7; `BUILD.md` shows where to inject a manual clock to single-step.
- EPROM/EEPROM programmer with independent read-back. Compare read-back against `_build/rom/SHA256SUMS`.

## 4. Build in phases

`wiring/BUILD.md` is the checklist. The phases are the spec's own sequence:

| Phase | Fit | Prove |
|---|---|---|
| 1 | Rails, bulk capacitors, regulator fixture | 5 V on every rail half |
| 2 | U5, U6, U7, U11, U45, U42 and the RC parts | Master clock ≤600 kHz, six Johnson states, reset release order |
| 3 | U1, U3, U4, U44, U8–U13, U18, pull-ups | Reset vector fetch, Section 11.2 handoffs |
| 4 | U2 | Diagnostic loop at $0200, handoffs again |
| 5 | U14–U17, switch panel | DIP byte, keys, one WR_GPIO_N edge per store |
| 6 | U19, U20, U21, digit 0 | Segment map, current, legibility |
| 7 | U22–U36, digits 1–15 | Font page, lamp test, rail under full load |
| 8 | BB9 (U37–U41), status LEDs; remove straps | Section 11.4 lock and fault table |

Each phase lists the inputs it leaves floating. Five of them are the straps the spec prescribes for a missing lock board; four more (U11 pins 12 and 13, U45 pin 2, U18 pin 2) fall out of the ordering and are tied low until their driver arrives.

For every measurement there is a simulated reference: `python3 -m sim run <scenario> --vcd out.vcd` or `python3 -m sim diag --vcd out.vcd` writes a waveform of what the scope should show, including the pin-level timing of every IC.

## 5. Decisions to make before firmware

- **Signing time.** The reference firmware needs about 0.68 × 10⁹ cycles for the spec's full flow: 2–4 hours at the spec's 13–88 kHz CPU clock, 11 minutes at 1 MHz (`FINDINGS.md` F11). The 100 kHz ceiling is a breadboard signal-integrity margin, not a logic limit; the simulation runs clean with an 8 MHz master. Bring the board up at the spec clock, pass Section 11.2, then decide whether to qualify a faster master (a canned oscillator into U6/U45 pin 3/11 in place of the RC) or accept the wait.
- **Firmware scope.** The signer ROM covers Sections 10.2–10.4 (envelope, double signature, verification, result record, locks). The review UI, seed entry and the Solana/Squads policy parser (Section 10.5) are not written; they are the firmware work after the hardware passes Section 11.4.
- **What this build is.** A public-key signer on a solderless board. The live-key requirements in Section 12 (independent wipe, power isolation, soldered construction) are a later revision.
