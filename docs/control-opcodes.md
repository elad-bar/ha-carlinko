# CarLinko remote-control opcodes — Blutter jump table

Recovered from Dart AOT (`send_vehicle_control_data_utils.dart::assembledSendData`) plus
`vcLoadingMessage` / `VehicleControlActionEnum` labels. These are the `data` values for
`POST /user/vehicle/remoteControl`.

**Live-confirmed on this project:** A/C on `741001` / off `741000` (2026-08). Stop charging
`742701` was previously confirmed from an app log string. Other rows are **Blutter-mapped** —
verify on an awake car before trusting them.

**Runtime wiring:** hex for integrated controls lives on
[`EntitySpec.commands`](../custom_components/carlinko/models/entity_specs.py)
(action → opcode). This document is the **complete** named-key catalog (used and unused).

Verify by calling `ApiClient.send_control(hex)` from `engine/` or `EntityPublisher.log_command(key, action)`.

## Format

```
74 <CMD> <STATE>        (6 hex chars; temp set is 7411 + °C byte)
  74      = control-command prefix
  <CMD>   = command id
  <STATE> = 00 off/close · 01 on/open · 02/03 extra mode/level
```

Init handshake (no actuation): `2301`, `24`, `77` — send `77` before an actuation (not yet automated in `ApiClient.send_control`).

## Jump-table index → action → opcode

| Index | Action | Opcode | Confidence |
|------:|--------|--------|------------|
| 0 | door lock | `740100` | blutter |
| 1 | door unlock | `740200` | blutter |
| 2 | windows close | `740500` | blutter |
| 3 | windows vent | `740E00` | blutter |
| 4 | windows open | `740600` | blutter |
| 5 | trunk/liftgate open | `740300` | blutter |
| 6 | trunk/liftgate close | `740A00` | blutter |
| 7 | find car | `740400` | blutter |
| 8 | sunroof close | `740F00` | blutter |
| 9 | sunroof raise/tilt | `740F02` | blutter |
| 10 | sunroof open | `740F01` | blutter |
| 11 | engine on | `740700` | blutter |
| 12 | engine off | `740800` | blutter |
| 13 | temp set | `7411` + °C byte | blutter |
| 14 | A/C on | `741001` | **live** |
| 15 | A/C off | `741000` | **live** |
| 16–17 | quick heat on/off | `741F01` / `741F00` | blutter |
| 18–19 | quick cool on/off | `742001` / `742000` | blutter |
| 20–21 | air purify on/off | `742501` / `742500` | blutter |
| 22–23 | front defog on/off | `741201` / `741200` | blutter |
| 24–27 | L windshield / steering heat family | `7423xx` / `7424xx` | blutter |
| 36–37 | steering heat on/off | `742401` / `742400` | blutter |
| 46–51 | L seat heat L1–L3 / off | `741501`–`741503` / `741500` | blutter |
| 52–57 | L seat vent | `741A01`–`741A03` / `741A00` | blutter |
| 58–63 | L rear heat | `741701`–`741703` / `741700` | blutter |
| 64–69 | L rear vent | `741C01`–`741C03` / `741C00` | blutter |
| 70–75 | R seat heat | `741601`–`741603` / `741600` | blutter |
| 76–81 | R seat vent | `741B01`–`741B03` / `741B00` | blutter |
| 82–87 | R rear heat | `741901`–`741903` / `741900` | blutter |
| 88–93 | R rear vent | `741E01`–`741E03` / `741E00` | blutter |
| 95 | stop charging | `742701` | **live** (app log) |
| 96–97 | gear high / low | `742602` / `742600` | blutter |
| 98–99 | BLE lock / unlock | same as 0/1 | alias |

Indices ~28–35 (generic seat On/Off) are **incomplete in the binary** (some Off cases return
`""` and send nothing). Use the leveled `*1`/`*2`/`*3` / `*Off` commands instead.

## Function-ID cheat sheet

| ID | Feature |
|----|---------|
| 01/02 | lock / unlock |
| 03/0A | trunk open / close |
| 04 | find car |
| 05/06/0E | windows close / open / vent |
| 07/08 | engine on / off |
| 0F | sunroof |
| 10 | A/C |
| 11 | temperature |
| 12 | front defog |
| 15/16 | L/R seat heat |
| 17/19 | L/R rear heat |
| 1A/1B | L/R seat vent |
| 1C/1E | L/R rear vent |
| 1F/20 | quick heat / cool |
| 23/24 | windshield / steering heat |
| 25 | air purify |
| 26/27 | gear / stop charge |

## Named keys (complete)

Blutter assembledSendData jump table (2026-08). **Entity spec** = `EntitySpec.key` in
[`entity_specs.py`](../custom_components/carlinko/models/entity_specs.py) when that hex is
wired via `commands`; **—** = doc-only.

| Name | Opcode | Entity spec |
|------|--------|-------------|
| lock | `740100` | lock |
| unlock | `740200` | lock |
| liftOpen | `740300` | liftgate |
| liftClose | `740A00` | liftgate |
| find | `740400` | find |
| winClose | `740500` | windows |
| winOpen | `740600` | windows |
| winVent | `740E00` | windows |
| roofClose | `740F00` | sunroof |
| roofTilt | `740F02` | sunroof |
| roofOpen | `740F01` | sunroof |
| engineOn | `740700` | engine |
| engineOff | `740800` | engine |
| acOn | `741001` | climate |
| acOff | `741000` | climate |
| acQuickHeatOn | `741F01` | quick_heat |
| acQuickHeatOff | `741F00` | — |
| acQuickCoolOn | `742001` | quick_cool |
| acQuickCoolOff | `742000` | — |
| acPurifyOn | `742501` | purify |
| acPurifyOff | `742500` | purify |
| defrostOn | `741201` | defrost_cmd |
| defrostOff | `741200` | defrost_cmd |
| windshieldHeatOn | `742301` | — |
| windshieldHeatOff | `742300` | — |
| steerHeatOn | `742401` | — |
| steerHeatOff | `742400` | — |
| steerHeatLOn | `742401` | — |
| steerHeatLOff | `742400` | — |
| steerHeatROn | `742401` | — |
| steerHeatROff | `742400` | — |
| seatHeatLOff | `741500` | seat_heatL |
| seatHeatL1 | `741501` | seat_heatL |
| seatHeatL2 | `741502` | seat_heatL |
| seatHeatL3 | `741503` | seat_heatL |
| seatVentLOff | `741A00` | seat_ventL |
| seatVentL1 | `741A01` | seat_ventL |
| seatVentL2 | `741A02` | seat_ventL |
| seatVentL3 | `741A03` | seat_ventL |
| seatHeatLROff | `741700` | seat_heatLR |
| seatHeatLR1 | `741701` | seat_heatLR |
| seatHeatLR2 | `741702` | seat_heatLR |
| seatHeatLR3 | `741703` | seat_heatLR |
| seatVentLROff | `741C00` | seat_ventLR |
| seatVentLR1 | `741C01` | seat_ventLR |
| seatVentLR2 | `741C02` | seat_ventLR |
| seatVentLR3 | `741C03` | seat_ventLR |
| seatHeatROff | `741600` | seat_heatR |
| seatHeatR1 | `741601` | seat_heatR |
| seatHeatR2 | `741602` | seat_heatR |
| seatHeatR3 | `741603` | seat_heatR |
| seatVentROff | `741B00` | seat_ventR |
| seatVentR1 | `741B01` | seat_ventR |
| seatVentR2 | `741B02` | seat_ventR |
| seatVentR3 | `741B03` | seat_ventR |
| seatHeatRROff | `741900` | seat_heatRR |
| seatHeatRR1 | `741901` | seat_heatRR |
| seatHeatRR2 | `741902` | seat_heatRR |
| seatHeatRR3 | `741903` | seat_heatRR |
| seatVentRROff | `741E00` | seat_ventRR |
| seatVentRR1 | `741E01` | seat_ventRR |
| seatVentRR2 | `741E02` | seat_ventRR |
| seatVentRR3 | `741E03` | seat_ventRR |
| chgStop | `742701` | charge_stop |
| gearHigh | `742602` | gear |
| gearLow | `742600` | gear |

Temp set uses builder `7411` + °C byte (not a fixed named key). BLE lock/unlock reuse `740100` / `740200`.

## Old guess map (removed in v2)

The previous best-effort wiring was **wrong** (e.g. A/C was `742401`, which is steering heat;
`liftOpen` was `741201`, which is front defog). Do not reuse those hex values for the old labels.

## How to re-verify

1. Car awake, cellular online.
2. `opcode_for_entity("lock", "unlock")` or `ApiClient.send_control("740200")` in `engine/`.
3. Optional: compare live telemetry bytes (`b23` A/C, `b26` engine_on candidate, `b5` HV) before and after.
