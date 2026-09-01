# Carlinko HTTP API contracts

Source: Flutter client decompile (`HttpRequestInterface` + request/response beans).

## Common

| Item      | Value                                                                |
| --------- | -------------------------------------------------------------------- |
| Host      | `https://cqr-api-{region}.hzhjcl.com` (e.g. `sea`, `saf`, `emea`, …) |
| Envelope  | `{ "code": string, "msg": string, "data": … }`                       |
| Success   | `code == "0000"`                                                     |
| Auth fail | `code == "9997"` (token invalid → re-login)                          |

### Signed headers (most authenticated calls)

| Header      | Notes                                             |
| ----------- | ------------------------------------------------- |
| `Language`  | App language                                      |
| `token`     | From login (`data`); **omitted on `/user/login`** |
| `timestamp` | Corrected UTC milliseconds (string/number)        |
| `signature` | `SecureSignUtils.signMethod` over sign payload    |
| `version`   | App/API version                                   |
| _(extra)_   | From `AddHearUtils.addRequestHearParas`           |

POST JSON bodies usually also include a `timestamp` field used for signing.

### HA / engine client fidelity (`ApiClient`)

| Item             | Behavior                                                                                 |
| ---------------- | ---------------------------------------------------------------------------------------- |
| Body `timestamp` | Included on `login`, `remoteControl`, and `deviceLocate`                                 |
| `version` header | Sent as app version (`1.12.0`) on signed requests + login                                |
| `isOnline` sign  | `{ "id": "<vehicleId>", "timestamp": "…" }` (path id; not a query param)                 |
| Clock skew       | `GET /pub/timestamp` adjusts `now_ms()`                                                  |
| WS URL           | `GET /netty/getConnect/2/{deviceSn}` before connect; region template fallback            |
| REST telemetry   | `GET /user/vehicle/state/{vehicleId}` when WS disconnected                               |
| OTA              | Read-only `higherFirmware` only — **`startUpgradeFirmware` is out of integration scope** |

---

## 1. `POST /user/login`

**Auth:** none (no `token` header)
**Content-Type:** `application/json`
**Client:** `HttpRequestInterface.loginHandler` → `LoginParams`

### Request body

```json
{
  "account": "<phone or email>",
  "appType": "APP",
  "appVersion": "<app version>",
  "dateTime": "<client datetime>",
  "language": "<lang>",
  "md5": "",
  "method": "PASSWORD",
  "osType": "ANDROID",
  "osVersion": "<os version>",
  "password": "<password>",
  "phoneBrand": "<brand>",
  "phoneModel": "<model>",
  "timeZone": "<tz>",
  "verifyCode": "",
  "appName": "<app name>",
  "timestamp": "<corrected utc ms>"
}
```

Password login hardcodes `method: "PASSWORD"` and empty `md5` / `verifyCode`.

### Response

```json
{
  "code": "0000",
  "msg": "...",
  "data": "<auth token string>"
}
```

App stores `data` as local `token`.

---

## 2. `GET /user/vehicle`

**Auth:** signed headers + token
**Content-Type:** `application/x-www-form-urlencoded`
**Body / query:** none
**Client:** `getVehicleList` → `VehicleListResultBean`

### Response

```json
{
  "code": "0000",
  "msg": "...",
  "data": [
    /* VehicleData */
  ]
}
```

### `VehicleData` fields

| Field                                                     | Role                                |
| --------------------------------------------------------- | ----------------------------------- |
| `vehicleId`                                               | Vehicle id                          |
| `licenseNumber`, `vin`                                    | Identity                            |
| `type`, `modelId`, `model`, `brand`, `brandAlias`, `year` | Model                               |
| `areaCode`, `airDuration`                                 | Region / AC                         |
| `deviceId`, `deviceName`                                  | Device id / SN                      |
| `beginTime`, `endTime`                                    | Binding window                      |
| `remoteControls`                                          | Remote control capability flags     |
| `vehicleControlConfig`                                    | Control config                      |
| `vehicleImgConfig`, `vehicleImgConfigs`                   | Images                              |
| `keyConfigData`                                           | Key config                          |
| `repairing`, `default`, `owner`                           | Flags (`default` = default vehicle) |
| `servicePackage`, `countryBrandId`, `simExpiredTime`      | Service / SIM                       |

Registry/profile only — not live GPS or live control status.

---

## 3. `POST /user/vehicle/remoteControl`

**Auth:** signed headers + token
**Content-Type:** `application/json`
**Client:** `sendVehicleControlCmd` → `SendVehicleControlParams` → `BaseResultBean`

### Request body

```json
{
  "vehicleId": "<vehicleId>",
  "deviceSn": "<device SN>",
  "data": "<opcode hex string>",
  "timeOut": 20,
  "timestamp": "<corrected utc ms>"
}
```

| Field     | Notes                                                                                            |
| --------- | ------------------------------------------------------------------------------------------------ |
| `data`    | Control opcode hex (e.g. `740100` lock). See `out/asm/carlinko/tools/vehicle_control_opcodes.md` |
| `timeOut` | App default **20** (seconds)                                                                     |

### Response

```json
{
  "code": "0000",
  "msg": "...",
  "data": null
}
```

Success is primarily `code == "0000"`. Actual vehicle state is refreshed via WebSocket action `6` / BLE, not this response body.

---

## 4. `POST /maps/deviceLocate`

**Auth:** signed headers + token
**Content-Type:** `application/json`
**Client:** `getVehiclePositioningData` → `VehiclePositioningParams` → `VehicleLocationResultBean`

### Request body

```json
{
  "sn": "<device SN>",
  "showAddress": 1,
  "timestamp": "<corrected utc ms>"
}
```

`showAddress` defaults to `1` in the app. Use device SN, not `vehicleId`.

### Response

```json
{
  "code": "0000",
  "msg": "...",
  "data": {
    "address": "...",
    "lat": 0.0,
    "lng": 0.0
  }
}
```

| Code    | Meaning                                              |
| ------- | ---------------------------------------------------- |
| `50052` | Location query failed (offline / no fix / bad SN, …) |

---

## 5. `GET /user/vehicle/isOnline/{vehicleId}`

**Auth:** signed headers + token
**Content-Type:** `application/x-www-form-urlencoded`
**Client:** `queryDeviceOnline` → `BaseResultBean`

### Path

`/user/vehicle/isOnline/{vehicleId}`

### Sign payload (headers only; no body)

```json
{
  "id": "<vehicleId>",
  "timestamp": "<corrected utc ms>"
}
```

### Response

```json
{
  "code": "0000",
  "msg": "...",
  "data": true
}
```

`data` is a **boolean** (`true` = online). Log label in app: “判断设备是否在线”.

---

## 6. `GET /user/notice/unReadCount`

**Auth:** signed headers + token
**Content-Type:** `application/x-www-form-urlencoded`
**Client:** message-center summary → `MessageCenterResultBean`

### Query

| Variant     | Path                                             |
| ----------- | ------------------------------------------------ |
| Global      | `/user/notice/unReadCount`                       |
| Per vehicle | `/user/notice/unReadCount?vehicleId={vehicleId}` |

### Response

```json
{
  "code": "0000",
  "msg": "...",
  "data": {
    "systemNoticeVo": {
      "contents": "...",
      "count": 0,
      "createdTime": "...",
      "type": 1,
      "icon": "...",
      "display": true
    },
    "vehicleNoticeVo": {
      "contents": "...",
      "count": 0,
      "createdTime": "...",
      "type": 2,
      "icon": "...",
      "display": true
    },
    "controlNoticeVo": {
      "contents": "...",
      "count": 0,
      "createdTime": "...",
      "type": 4,
      "icon": "...",
      "display": true
    },
    "serviceNoticeVo": {
      "contents": "...",
      "count": 0,
      "createdTime": "...",
      "type": 5,
      "icon": "...",
      "display": true
    },
    "servicePackageVo": {
      "contents": "...",
      "count": 0,
      "createdTime": "...",
      "type": 0,
      "icon": "...",
      "display": true
    }
  }
}
```

Each `*Vo` bucket: `contents`, `count`, `createdTime`, `type`, `icon`, `display`.

---

## 7. `GET /user/notice/page`

**Auth:** signed headers + token
**Content-Type:** `application/x-www-form-urlencoded`
**Client:** notice list → `MessageDetailsResultBean`

### Query

With vehicle:

```
/user/notice/page?page={page}&size=20&type={type}&vehicleId={vehicleId}
```

Without vehicle:

```
/user/notice/page?page={page}&size=20&type={type}
```

| Param       | Notes                                                               |
| ----------- | ------------------------------------------------------------------- |
| `page`      | Page number                                                         |
| `size`      | App hardcodes **20**                                                |
| `type`      | Notice bucket type (e.g. 1 system, 2 vehicle, 4 control, 5 service) |
| `vehicleId` | Optional                                                            |

### Response

```json
{
  "code": "0000",
  "total": 0,
  "data": [
    {
      "noticeId": "...",
      "title": "...",
      "contents": "...",
      "createdTime": "...",
      "extra": "...",
      "isRead": false,
      "operation": "..."
    }
  ]
}
```

---

## 8. `GET /user/maintain/page`

**Auth:** signed headers + token
**Content-Type:** `application/x-www-form-urlencoded`
**Client:** `MaintenanceListBean` / `MaintainData`

### Query

```
/user/maintain/page?vehicleId={vehicleId}&queryKey={queryKey}&page={page}&size=20
```

| Param       | Notes                               |
| ----------- | ----------------------------------- |
| `vehicleId` | Required                            |
| `queryKey`  | Search/filter string (may be empty) |
| `page`      | Page number                         |
| `size`      | App hardcodes **20**                |

### Response

```json
{
  "code": "0000",
  "total": 0,
  "data": [
    {
      "maintainId": "...",
      "vehicleId": "...",
      "maintainProject": "...",
      "maintainExtent": 0,
      "nextMaintainExtent": 0,
      "maintainDate": "...",
      "nextMaintainDate": "..."
    }
  ]
}
```

---

## 9. `GET /user/maintain/details/{maintainId}`

**Auth:** signed headers + token
**Content-Type:** `application/x-www-form-urlencoded`
**Client:** `MaintenanceDetailsBean` / `MaintenanceData`

### Path

`/user/maintain/details/{maintainId}`

### Response

```json
{
  "code": "0000",
  "msg": "...",
  "data": {
    "vehicleId": "...",
    "maintainProject": "...",
    "maintainExtent": 0,
    "maintainDate": "...",
    "nextMaintainExtent": 0,
    "nextMaintainDate": "...",
    "maintainAccessoryTime": "...",
    "logList": [
      {
        "id": "...",
        "dealerName": "...",
        "maintainProject": "...",
        "maintainContent": "...",
        "maintainExtent": 0,
        "maintainDate": "...",
        "nextMaintainExtent": 0,
        "nextMaintainDate": "...",
        "maintainAccessoryTime": "...",
        "status": 0
      }
    ]
  }
}
```

---

## 10. `GET /user/higherFirmware`

**Auth:** signed headers + token
**Content-Type:** `application/x-www-form-urlencoded`
**Client:** `getFirmwareHighVersion` → `FirmwareInfoBean`

### Query

```
/user/higherFirmware?deviceId={deviceId}&version={currentFirmwareVersion}
```

### Sign payload

```json
{
  "deviceId": "<deviceId>",
  "version": "<currentFirmwareVersion>",
  "timestamp": "<corrected utc ms>"
}
```

### Response

```json
{
  "code": "0000",
  "msg": "...",
  "data": {
    "firmwareId": "...",
    "version": "...",
    "upgradeType": 0,
    "type": 0,
    "path": "...",
    "upgrading": false,
    "deviceId": "...",
    "blePath": "..."
  }
}
```

Used to check whether a newer firmware exists before showing OTA / `startUpgradeFirmware`. App may throttle repeated checks (~3s).

**Integration scope:** HA/engine only call this read-only check. Starting an upgrade (`startUpgradeFirmware`) is **not** implemented.

---

## 11. `GET /pub/timestamp`

**Auth:** none
**Client:** clock skew correction (`VerifyTimestampUtils` equivalent)

### Response

```json
{
  "code": "0000",
  "msg": "...",
  "data": 1782017645767
}
```

`data` = server epoch milliseconds. Client stores `skew = server − local` and applies it in signed `timestamp` values.

---

## 12. `GET /netty/getConnect/2/{deviceSn}`

**Auth:** signed headers + token
**Client:** resolve realtime WebSocket base URL

### Path

`/netty/getConnect/2/{deviceSn}`

### Response

```json
{
  "code": "0000",
  "msg": "...",
  "data": "ws://wss-cqr-{region}.hzhjcl.com:4002"
}
```

`data` may be an `http(s)://…:4002` URL string; the client rewrites it to `ws(s)://` and normalizes a trailing `/`. On failure the integration falls back to the region WS template.

---

## 13. `GET /user/vehicle/state/{vehicleId}`

**Auth:** signed headers + token
**Client:** REST telemetry (same hex blob as WebSocket `action:6`)

### Path

`/user/vehicle/state/{vehicleId}`

### Sign payload (headers only; no body)

```json
{
  "id": "<vehicleId>",
  "timestamp": "<corrected utc ms>"
}
```

### Response

```json
{
  "code": "0000",
  "msg": "...",
  "data": "<telemetry hex blob>"
}
```

Blob layout: see [api-map.md](api-map.md) (WS action 6). HA polls this only while that vehicle’s WebSocket is disconnected.

---

## Quick reference

| Method | Path                                  | Body / query highlight                          | `data` shape                |
| ------ | ------------------------------------- | ----------------------------------------------- | --------------------------- |
| POST   | `/user/login`                         | `LoginParams` + `timestamp`                     | token string                |
| GET    | `/user/vehicle`                       | —                                               | `VehicleData[]`             |
| POST   | `/user/vehicle/remoteControl`         | `vehicleId`, `deviceSn`, `data`, `timeOut`      | usually null                |
| POST   | `/maps/deviceLocate`                  | `sn`, `showAddress`                             | `{ address, lat, lng }`     |
| GET    | `/user/vehicle/isOnline/{vehicleId}`  | path id; sign `id`                              | `boolean`                   |
| GET    | `/user/notice/unReadCount`            | optional `vehicleId`                            | message-center VOs          |
| GET    | `/user/notice/page`                   | `page`, `size=20`, `type`, optional `vehicleId` | notice list + `total`       |
| GET    | `/user/maintain/page`                 | `vehicleId`, `queryKey`, `page`, `size=20`      | maintain list + `total`     |
| GET    | `/user/maintain/details/{maintainId}` | path id                                         | maintain detail + `logList` |
| GET    | `/user/higherFirmware`                | `deviceId`, `version`                           | `FirmwareInfoBean`          |
| GET    | `/pub/timestamp`                      | —                                               | epoch ms                    |
| GET    | `/netty/getConnect/2/{deviceSn}`      | path SN                                         | WS URL string               |
| GET    | `/user/vehicle/state/{vehicleId}`     | path id; sign `id`                              | telemetry hex               |
