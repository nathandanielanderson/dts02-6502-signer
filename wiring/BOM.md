# DTS-02 bill of materials (generated)

## How to order

1. **Semiconductors and digits: one distributor cart.** Upload `order_mouser.csv` (manufacturer part number, quantity with spares) to Mouser's BOM tool, or paste the numbers into DigiKey; both carry every line. Amazon listings for these parts are resellers at a markup or unverifiable pulls, and the exact TI family (HC, HCT, AC) matters here. Cheaper option with slower shipping: Tayda Electronics stocks most 74HC/HCT DIPs for a fraction of the price; check each part number.
2. **Everything else: Amazon** (or any hobby supplier). The list below has the quantities with spares. Generic 0.56-inch common-cathode red digits (the `5161AS` type) share the SC56-11EWA pinout and are an acceptable fallback if the Kingbright part is back-ordered; phase 6 of `BUILD.md` checks one digit before the panel is soldered either way.
3. **Order the memories and digits first**; they have shown the longest lead times.

### Amazon list

| Qty | Search for | What to check |
|---|---|---|
| 11 | BusBoard BB830 breadboard (or a 10-pack of 830-tie boards) | 830 tie points, 63 rows, 0.6-inch gap between the two halves so the CPU and memories fit in c/g. The layout already includes rail bridge wires, so split or continuous power rails both work. Avoid the cheapest clones: loose rail contacts cause intermittent resets. |
| 2 kits | Elenco 140-piece pre-formed jumper wire kit | 22 AWG solid, 14 lengths up to 5 in; two kits cover the ~460 wires under 130 mm. |
| 1 set | 22 AWG solid core hookup wire, 6 colours, spools | Solid, not stranded. Red and black for power plus four signal colours; about 25 m per colour covers the ~200 longer runs with slack. |
| 2 packs of 100 | 3.3k ohm 1/4 W resistors, pack of 100 | 128 installed. 5 % carbon film or 1 % metal film, both fine. |
| 1 pack of 100 each | 10k ohm and 220 ohm 1/4 W resistors, pack of 100 | 27 and 20 installed; assortment kits rarely hold enough of one value. |
| 1 kit | 1/4 W resistor assortment kit (metal film) | Must include 4.7k (12 needed), 1k (8) and 100k (1). |
| 1 pack of 100 | 0.1uF 50V ceramic capacitors (marked 104) | 50 installed. Short leads, through-hole. |
| 1 pack of 20 | 10uF 25V electrolytic capacitors | 10 installed, one per board. |
| 1 kit | Electrolytic capacitor assortment | Needs 1uF, 47uF and 100uF; 25 V rating for the 100uF. |
| 1 kit | Ceramic disc capacitor assortment (C0G/NP0) | Must contain 560 pF (561), 680 pF (681) or 1 nF (102) for the oscillator, and 330 nF (334) or buy a 0.33uF film capacitor separately. |
| 1 pack | 1N4148 diodes, pack of 100 | One installed. |
| 1 pack | 1N5819 Schottky diodes, pack of 20 | One installed, battery reverse protection. |
| 1 pack each | 3mm red LEDs; 3mm yellow LEDs | One red (FAULT) and two yellow (locks). |
| 1 pack | 6x6mm tactile pushbuttons, 4-pin, breadboard friendly, pack of 50 | 6 installed. |
| 1 pack | 8-position DIP switch, 2.54 mm pitch | One installed; the pack gives spares. |
| 1 | TO-220 heatsink with clip | Under 15 C/W; the L7805ACV is already in the Mouser cart. |
| 1 each | Panel-mount 5x20mm fuse holder; 500mA 5x20mm fuses; SPST toggle switch; 8xAA battery holder with leads | Battery fixture (spec Section 5.1); can wait until the board runs on the bench supply. |
| 1 | 12x18 cm double-sided prototype PCB, 2.54 mm | LED panel as two rows of eight digits (spec Section 2.2 allows this): each row needs 48 columns (122 mm) for the digits plus room above for the 64 segment resistors mounted upright. A single row of all 16 digits needs 244 mm, which only a 20x30 cm board cut down to about 25x5 cm gives. |
| 1 | 5x7 cm double-sided prototype PCB, 2.54 mm | Power fixture: regulator, supervisor, capacitors, bleeder, diode and screw terminals. Usually sold in multi-size packs that include the 12x18 cm board. |
| 1 pack | 5.08 mm 2-pin screw terminal blocks | Battery and regulator fixture connections. |
| 1 | XGecu TL866II Plus or T48 programmer | Either programs both ROM types (AT27C256R and AT28C256 are in the device list). XGecu's Xgpro software is Windows-only; the open-source minipro tool covers both models on macOS and Linux. |

### Bench tools (not parts)

| Tool | Why |
|---|---|
| 5 V bench power supply with adjustable current limit | Phases 1 to 7; a plain 5 V adapter works for the first boards but cannot limit a wiring mistake. |
| 8-channel USB logic analyzer (24 MHz class) | Decodes the address and data buses at the 13 to 88 kHz CPU clock; enough to see the reset vector fetch. |
| Oscilloscope, 100 MHz class, with a probe ground spring | Required for the 5 ns PHI2 edge and the Section 11.2 handoff checks; a logic analyzer cannot substitute. |

### Distributor cart (`order_mouser.csv`)

| Order qty | Installed | Manufacturer part | For |
|---:|---:|---|---|
| 1 | 1 | W65C02S6TPG-14 | U1 |
| 2 | 1 | AS6C62256-55PCN | U2 |
| 3 | 1 | AT27C256R-45PU | U3 |
| 4 | 3 | SN74HCT541N | U4, U14, U15 |
| 3 | 2 | SN74HC14N | U5, U17 |
| 5 | 4 | SN74HCT74N | U6, U37, U38, U45 |
| 2 | 1 | SN74AC14N | U7 |
| 2 | 1 | SN74HCT04N | U8 |
| 2 | 1 | CD74HC30E | U9 |
| 2 | 1 | SN74HCT00N | U10 |
| 3 | 2 | SN74HCT08N | U11, U40 |
| 3 | 2 | SN74HCT32N | U12, U41 |
| 2 | 1 | SN74HCT138N | U13 |
| 2 | 1 | SN74HCT273N | U16 |
| 2 | 1 | CD74HC10E | U18 |
| 3 | 2 | SN74HCT244N | U19, U20 |
| 18 | 16 | SN74HC595N | U21–U36 |
| 2 | 1 | CD74HCT157E | U39 |
| 1 | 1 | MCP130-460DI/TO | U42 |
| 1 | 1 | L7805ACV | U43 |
| 2 | 1 | SN74HCT573N | U44 |
| 18 | 16 | SC56-11EWA | Kingbright SC56-11EWA common-cathode digit |
| 1 | 1 | AT28C256-15PU | U3 (dev) |

Generated by `python3 -m sim wiring`. IC lines come from spec Section 2.1; discrete quantities are counted from the layout in `WIRING.md` (which `python3 -m sim check` reconciles with Section 2.2); construction items are Section 2.2. `bom.csv` is the same list for a spreadsheet.

The *Distributor search* column is a Mouser part-number pattern, not a stock claim: only the WDC CPU number was confirmed on a live product page; the rest follow Mouser's maker prefixes and must be checked before ordering. DigiKey carries the Kingbright digit. Do not substitute 74LS or a surface-mount suffix; the timing review assumes the listed families (Section 2.1).

*Hobby stock* marks items a builder with a Ben Eater style 8-bit or 6502 breadboard kit usually has already; check quantities, because this design uses far more of some values.

## Integrated circuits

| Qty | Item | Detail | Refs | Vendor | Distributor search | Hobby stock |
|---:|---|---|---|---|---|---|
| 1 | WDC W65C02S6TPG-14 | PDIP-40, 0.6 in; CPU | U1 | Mouser / DigiKey | 955-W65C02S6TPG-14 (verified) | yes |
| 1 | Alliance AS6C62256-55PCN | PDIP-28, 0.6 in; 32 KiB SRAM; select exact qualified suffix | U2 | Mouser / DigiKey | 913-AS6C62256-55PCN | yes |
| 1 | Microchip AT27C256R-45PU | PDIP-28, 0.6 in; 32 KiB OTP ROM; buy at least 3 blanks for development | U3 | Mouser / DigiKey | 579-AT27C256R-45PU |  |
| 1 | TI SN74HCT541N | PDIP-20; WBUF: CPU→peripheral write buffer, enabled only in PHI2-high write cycles | U4 | Mouser / DigiKey | 595-SN74HCT541N |  |
| 2 | TI SN74HC14N | PDIP-14; Clock/reset Schmitt gates; button conditioning | U5, U17 | Mouser / DigiKey | 595-SN74HC14N |  |
| 4 | TI SN74HCT74N | PDIP-14; PHASE Johnson counter; two lock/fault packages; cycle-direction register and third Johnson stage | U6, U37, U38, U45 | Mouser / DigiKey | 595-SN74HCT74N |  |
| 1 | TI SN74AC14N | PDIP-14; Fast CPU clock buffer and separate fault-latch clock; actual edge qualification required | U7 | Mouser / DigiKey | 595-SN74AC14N |  |
| 1 | TI SN74HCT04N | PDIP-14; INV: bus/address inversions | U8 | Mouser / DigiKey | 595-SN74HCT04N |  |
| 1 | TI CD74HC30E | PDIP-14; PAGE: eight-input NAND for $7Fxx decode | U9 | Mouser / DigiKey | 595-CD74HC30E |  |
| 1 | TI SN74HCT00N | PDIP-14; NAND: RAM select, write window, hold term | U10 | Mouser / DigiKey | 595-SN74HCT00N |  |
| 2 | TI SN74HCT08N | PDIP-14; AND: timing/reset, latch output enable, protection predicates | U11, U40 | Mouser / DigiKey | 595-SN74HCT08N |  |
| 2 | TI SN74HCT32N | PDIP-14; OR: GPIO strobe, RAM write enable, security latches | U12, U41 | Mouser / DigiKey | 595-SN74HCT32N |  |
| 1 | TI SN74HCT138N | PDIP-16; PORT: eight I/O selects | U13 | Mouser / DigiKey | 595-SN74HCT138N |  |
| 2 | TI SN74HCT541N | PDIP-20; Byte/key input buffers; enables = port select AND read window | U14, U15 | Mouser / DigiKey | 595-SN74HCT541N |  |
| 1 | TI SN74HCT273N | PDIP-20; Eight-bit GPIO/display-control latch | U16 | Mouser / DigiKey | 595-SN74HCT273N |  |
| 1 | TI CD74HC10E | PDIP-14; Three-input NAND: default/fault display blanking and the read window | U18 | Mouser / DigiKey | 595-CD74HC10E |  |
| 2 | TI SN74HCT244N | PDIP-20; Display fanout | U19, U20 | Mouser / DigiKey | 595-SN74HCT244N |  |
| 16 | TI SN74HC595N | PDIP-16; One static segment register per display digit | U21–U36 | Mouser / DigiKey | 595-SN74HC595N |  |
| 1 | TI CD74HCT157E | PDIP-16; Select message/result bank lock | U39 | Mouser / DigiKey | 595-CD74HCT157E |  |
| 1 | Microchip MCP130-460DI/TO | TO-92, D bondout; Power supervisor; 4.35–4.60 V trip range | U42 | Mouser / DigiKey | 579-MCP130-460DI/TO |  |
| 1 | ST L7805ACV | TO-220; 5 V linear regulator for battery fixture | U43 | Mouser / DigiKey | 511-L7805ACV |  |
| 1 | TI SN74HCT573N | PDIP-20; RLATCH: peripheral→CPU read latch, transparent during EARLY | U44 | Mouser / DigiKey | 595-SN74HCT573N |  |

## Discrete parts

| Qty | Item | Detail | Refs | Vendor | Distributor search | Hobby stock |
|---:|---|---|---|---|---|---|
| 50 | 100 nF ceramic, ≥16 V, short leads |  |  | Amazon |  | yes |
| 10 | 10 µF electrolytic, ≥10 V |  |  | Amazon |  | yes |
| 1 | 560 pF C0G/NP0, ≥16 V (oscillator) |  |  | Amazon |  |  |
| 1 | 1 µF, ≥10 V (reset RC) |  |  | Amazon |  |  |
| 1 | 330 nF, ≥25 V (regulator input) |  |  | Amazon |  |  |
| 1 | 100 µF electrolytic, ≥25 V |  |  | Amazon |  |  |
| 1 | 47 µF electrolytic, ≥10 V |  |  | Amazon |  |  |
| 1 | 1N4148 signal diode |  |  | Amazon |  | yes |
| 1 | 1N5819 Schottky diode |  |  | Amazon |  |  |
| 16 | Kingbright SC56-11EWA common-cathode digit |  |  | Mouser / DigiKey | 604-SC56-11EWA (pattern; also DigiKey 2163728) |  |
| 3 | 3 mm LED (1 red FAULT, 2 yellow MESSAGE_LOCK / RESULT_LOCK) |  |  | Amazon |  | yes |
| 128 | 3.3 kΩ resistor, 5 % or better, ≥1/8 W |  |  | Amazon |  |  |
| 27 | 10 kΩ resistor, ≥1/8 W |  |  | Amazon |  | yes |
| 20 | 220 Ω resistor, ≥1/8 W |  |  | Amazon |  | yes |
| 12 | 4.7 kΩ resistor, ≥1/8 W |  |  | Amazon |  |  |
| 7 | 1 kΩ resistor, ≥1/8 W |  |  | Amazon |  | yes |
| 1 | 100 kΩ resistor, ≥1/8 W |  |  | Amazon |  |  |
| 1 | 1 kΩ resistor, 1/4 W (rail bleeder) |  |  | Amazon |  | yes |
| 1 | Eight-pole SPST DIP switch | 8 poles |  | Amazon |  | yes |
| 6 | Normally-open momentary pushbutton |  |  | Amazon |  | yes |

## Construction

| Qty | Item | Detail | Refs | Vendor | Distributor search | Hobby stock |
|---:|---|---|---|---|---|---|
| 10 | 830-tie, 63-row solderless breadboard (BB1–BB10); buy at least one spare |  |  | Amazon |  | yes |
| 1 | Passive perfboard about 250 × 30–50 mm for the LED panel |  |  | Amazon |  |  |
| 1 | Small perfboard plus screw terminals for the fused battery/regulator fixture |  |  | Amazon |  |  |
| 1 | TO-220 heatsink ≤15 °C/W with hardware |  |  | Amazon |  |  |
| 1 | 500 mA fuse and holder |  |  | Amazon |  |  |
| 1 | SPST power switch ≥1 A at 15 V DC |  |  | Amazon |  |  |
| 1 | Eight-AA holder plus eight alkaline AA cells |  |  | Amazon |  |  |
| 1 | 22 AWG solid hookup wire, several colours (red and black for power); about 86 m in total |  |  | Amazon |  | yes |

## Development only

| Qty | Item | Detail | Refs | Vendor | Distributor search | Hobby stock |
|---:|---|---|---|---|---|---|
| 1 | Microchip AT28C256-15PU | PDIP-28 EEPROM; reusable development ROM, see BUILD.md | U3 (dev) | Mouser / DigiKey | 579-AT28C256-15PU | yes |

