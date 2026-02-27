# PyDDLVector Robot Capability Map (Komplet)

Denne fil kortlaegger robotmulighederne i `pyddlvector` og underliggende Vector gRPC-protokol.

## Legend

- `RO`: read-only (laesning)
- `RW`: write/kommando (kan aendre robotadfaerd eller indstillinger)
- `Stream`: stream-RPC (RO stream eller bi-directional kontrol)
- `Implemented in module`: dedikeret helper/wrapper i `pyddlvector` (udover generisk klient)

## 1) Public API i modulet (allerede implementeret)

| Symbol | Type | RO/RW | Implementeret | Noter |
|---|---|---|---|---|
| `RobotConfig` | dataclass | RW | Yes | Runtime/sdk config for forbindelse |
| `SdkConfigStore` | class | RO | Yes | Laeser `sdk_config.ini` |
| `VectorClient` | class | RW | Yes | Async gRPC klient (`connect`, `rpc`, `run`, `unary_unary`) |
| `VectorFleet` | class | RW | Yes | Multi-robot client lifecycle |
| `RobotActivityTracker` | class | RO | Yes | Afleder user-facing activity fra events + `RobotState` |
| `describe_robot_activity` | function | RO | Yes | Direkte state->activity mapping |
| `RobotTelemetry` | dataclass | RO | Yes | Orientation/lift/IMU model |
| `TelemetryFilter` | class | RO | Yes | Rate-limit + quantization |
| `extract_robot_telemetry` | function | RO | Yes | Udtraekker telemetry fra `RobotState` |
| `CameraFrame` | dataclass | RO | Yes | Normaliseret JPEG frame |
| `extract_camera_frame` | function | RO | Yes | Parser `CameraFeedResponse` |
| `RobotStimulation` | dataclass | RO | Yes | Normaliseret stimulation payload |
| `parse_stimulation_info` | function | RO | Yes | Parser stimulation event |
| `RobotStatistics` | dataclass | RO | Yes | Normaliserede lifetime stats |
| `fetch_lifetime_statistics` | async function | RO | Yes | `PullJdocs(ROBOT_LIFETIME_STATS)` |
| `fetch_master_volume` | async function | RO | Yes | `PullJdocs(ROBOT_SETTINGS)` |
| `update_master_volume` | async function | RW | Yes | `SetMasterVolume` + fallback `UpdateSettings` |
| `fetch_official_session_token` | async function | RO | Yes | Officiel Anki login/session |
| `fetch_cert_for_official_serial` | async function | RO | Yes | Cert download fra official endpoint |
| `fetch_cert_for_wirepod_serial` | async function | RO | Yes | Cert download fra wire-pod |
| `fetch_cert_from_robot_tls` | async function | RO | Yes | Cert direkte fra robot TLS |
| `authenticate_robot_guid` | async function | RW | Yes | `UserAuthentication` |
| `provision_runtime_robot` | async function | RW | Yes | End-to-end provisioning |

## 2) Properties/attributter (datafelter)

### 2.1 `RobotState` (komplet)

Kilde: `messages.proto::RobotState` (leveres via `Event.robot_state`).

| Felt | Type | RO/RW | Beskrivelse |
|---|---|---|---|
| `pose` | `PoseStruct` | RO | Position + quaternion |
| `pose_angle_rad` | `float` | RO | Yaw i radianer |
| `pose_pitch_rad` | `float` | RO | Pitch i radianer |
| `left_wheel_speed_mmps` | `float` | RO | Venstre hjulhastighed |
| `right_wheel_speed_mmps` | `float` | RO | Hojre hjulhastighed |
| `head_angle_rad` | `float` | RO | Hovedvinkel |
| `lift_height_mm` | `float` | RO | Lift/fork-hoejde |
| `accel` | `AccelData` | RO | Accelerometer x/y/z |
| `gyro` | `GyroData` | RO | Gyroscope x/y/z |
| `carrying_object_id` | `int32` | RO | Objekt-ID der baeres |
| `carrying_object_on_top_id` | `int32` | RO | Markeret som ikke understottet i proto-kommentar |
| `head_tracking_object_id` | `int32` | RO | Objekt-ID der trackes |
| `localized_to_object_id` | `int32` | RO | Objekt-ID brugt til lokalisering |
| `last_image_time_stamp` | `uint32` | RO | Timestamp for sidste billede |
| `status` | `uint32` | RO | Bitmask (`RobotStatus`) |
| `prox_data` | `ProxData` | RO | Naerhedssensor |
| `touch_data` | `TouchData` | RO | Touch sensor |

### 2.2 Underfelter (komplet for ovenstaaende structer)

| Struktur | Felter | RO/RW |
|---|---|---|
| `PoseStruct` | `x,y,z,q0,q1,q2,q3,origin_id` | RO |
| `AccelData` | `x,y,z` | RO |
| `GyroData` | `x,y,z` | RO |
| `ProxData` | `distance_mm,signal_quality,unobstructed,found_object,is_lift_in_fov` | RO |
| `TouchData` | `raw_touch_value,is_being_touched` | RO |

### 2.3 `RobotStatus` bitflags (komplet)

| Flag | Hex | RO/RW | Betydning |
|---|---:|---|---|
| `ROBOT_STATUS_IS_MOVING` | `0x1` | RO | Robot er i bevaegelse |
| `ROBOT_STATUS_IS_CARRYING_BLOCK` | `0x2` | RO | Baerer block/cube |
| `ROBOT_STATUS_IS_PICKING_OR_PLACING` | `0x4` | RO | Pick/place aktivitet |
| `ROBOT_STATUS_IS_PICKED_UP` | `0x8` | RO | Robot er loftet |
| `ROBOT_STATUS_IS_BUTTON_PRESSED` | `0x10` | RO | Knap trykket |
| `ROBOT_STATUS_IS_FALLING` | `0x20` | RO | Falder |
| `ROBOT_STATUS_IS_ANIMATING` | `0x40` | RO | Animation aktiv |
| `ROBOT_STATUS_IS_PATHING` | `0x80` | RO | Pathfinding aktiv |
| `ROBOT_STATUS_LIFT_IN_POS` | `0x100` | RO | Lift i position |
| `ROBOT_STATUS_HEAD_IN_POS` | `0x200` | RO | Head i position |
| `ROBOT_STATUS_CALM_POWER_MODE` | `0x400` | RO | Calm/sleep mode |
| `ROBOT_STATUS_IS_ON_CHARGER` | `0x1000` | RO | Staar paa lader |
| `ROBOT_STATUS_IS_CHARGING` | `0x2000` | RO | Lader |
| `ROBOT_STATUS_CLIFF_DETECTED` | `0x4000` | RO | Kant/afgrund detekteret |
| `ROBOT_STATUS_ARE_WHEELS_MOVING` | `0x8000` | RO | Hjulene roterer |
| `ROBOT_STATUS_IS_BEING_HELD` | `0x10000` | RO | Holdes i haanden |
| `ROBOT_STATUS_IS_MOTION_DETECTED` | `0x20000` | RO | Motion detekteret |

### 2.4 Andre centrale payload-properties

| Payload | Felter | RO/RW |
|---|---|---|
| `BatteryStateResponse` | `battery_level,battery_volts,is_charging,is_on_charger_platform,suggested_charger_sec,cube_battery` | RO |
| `VersionStateResponse` | `os_version,engine_build_id` | RO |
| `CameraConfigResponse` | `focal_length_x,focal_length_y,center_x,center_y,fov_x,fov_y,min_camera_exposure_time_ms,max_camera_exposure_time_ms,min_camera_gain,max_camera_gain` | RO |
| `CaptureSingleImageResponse` | `frame_time_stamp,image_id,image_encoding,data` | RO |
| `PhotoResponse` | `success,image` | RO |
| `ThumbnailResponse` | `success,image` | RO |
| `CubesAvailableResponse` | `factory_ids[]` | RO |
| `PullJdocsResponse` | `named_jdocs[]` | RO |

## 3) Event types (komplet oneof i `shared.proto::Event`)

Alle nedenstaaende er RO event payloads:

- `time_stamped_status`
- `wake_word`
- `attention_transfer`
- `robot_observed_face`
- `robot_changed_observed_face_id`
- `object_event`
- `stimulation_info`
- `photo_taken`
- `robot_state`
- `cube_battery`
- `keep_alive`
- `connection_response`
- `jdocs_changed`
- `alexa_auth_event`
- `mirror_mode_disabled`
- `vision_modes_auto_disabled`
- `check_update_status_response`
- `user_intent`
- `robot_observed_motion`
- `robot_erased_enrolled_face`
- `robot_renamed_enrolled_face`
- `camera_settings_update`
- `unexpected_movement`

## 4) Komplet RPC-funktionskatalog (86 stk)

Alle kan kaldes via `VectorClient.rpc()`/`run()`.

| RPC | Request -> Response | Mode | Implemented in module | Noter |
|---|---|---|---|---|
| `ProtocolVersion` | `ProtocolVersionRequest` -> `ProtocolVersionResponse` | RO | Yes (VectorClient.connect handshake) |  |
| `SDKInitialization` | `SDKInitializationRequest` -> `SDKInitializationResponse` | RW | Yes (VectorClient.connect handshake) |  |
| `DriveWheels` | `DriveWheelsRequest` -> `DriveWheelsResponse` | RW | No (generic via VectorClient) |  |
| `PlayAnimationTrigger` | `PlayAnimationTriggerRequest` -> `PlayAnimationResponse` | RW | No (generic via VectorClient) |  |
| `PlayAnimation` | `PlayAnimationRequest` -> `PlayAnimationResponse` | RW | No (generic via VectorClient) |  |
| `ListAnimations` | `ListAnimationsRequest` -> `ListAnimationsResponse` | RO | No (generic via VectorClient) |  |
| `ListAnimationTriggers` | `ListAnimationTriggersRequest` -> `ListAnimationTriggersResponse` | RO | No (generic via VectorClient) |  |
| `MoveHead` | `MoveHeadRequest` -> `MoveHeadResponse` | RW | No (generic via VectorClient) |  |
| `MoveLift` | `MoveLiftRequest` -> `MoveLiftResponse` | RW | No (generic via VectorClient) |  |
| `StopAllMotors` | `StopAllMotorsRequest` -> `StopAllMotorsResponse` | RW | No (generic via VectorClient) |  |
| `DisplayFaceImageRGB` | `DisplayFaceImageRGBRequest` -> `DisplayFaceImageRGBResponse` | RW | No (generic via VectorClient) |  |
| `EventStream` | `EventRequest` -> `stream EventResponse` | Stream (RO) | Partial (activity/telemetry/stimulation helpers) |  |
| `ExternalAudioStreamPlayback` | `stream ExternalAudioStreamRequest` -> `stream ExternalAudioStreamResponse` | Stream (RW) | No (generic via VectorClient) |  |
| `BehaviorControl` | `stream BehaviorControlRequest` -> `stream BehaviorControlResponse` | Stream (RW) | No (generic via VectorClient) |  |
| `AssumeBehaviorControl` | `BehaviorControlRequest` -> `stream BehaviorControlResponse` | Stream (RW) | No (generic via VectorClient) |  |
| `CancelFaceEnrollment` | `CancelFaceEnrollmentRequest` -> `CancelFaceEnrollmentResponse` | RW | No (generic via VectorClient) |  |
| `RequestEnrolledNames` | `RequestEnrolledNamesRequest` -> `RequestEnrolledNamesResponse` | RW | No (generic via VectorClient) |  |
| `UpdateEnrolledFaceByID` | `UpdateEnrolledFaceByIDRequest` -> `UpdateEnrolledFaceByIDResponse` | RW | No (generic via VectorClient) |  |
| `EraseEnrolledFaceByID` | `EraseEnrolledFaceByIDRequest` -> `EraseEnrolledFaceByIDResponse` | RW | No (generic via VectorClient) |  |
| `EraseAllEnrolledFaces` | `EraseAllEnrolledFacesRequest` -> `EraseAllEnrolledFacesResponse` | RW | No (generic via VectorClient) |  |
| `SetFaceToEnroll` | `SetFaceToEnrollRequest` -> `SetFaceToEnrollResponse` | RW | No (generic via VectorClient) |  |
| `EnrollFace` | `EnrollFaceRequest` -> `EnrollFaceResponse` | RW | No (generic via VectorClient) |  |
| `EnableMarkerDetection` | `EnableMarkerDetectionRequest` -> `EnableMarkerDetectionResponse` | RW | No (generic via VectorClient) |  |
| `EnableFaceDetection` | `EnableFaceDetectionRequest` -> `EnableFaceDetectionResponse` | RW | No (generic via VectorClient) |  |
| `EnableMotionDetection` | `EnableMotionDetectionRequest` -> `EnableMotionDetectionResponse` | RW | No (generic via VectorClient) |  |
| `EnableMirrorMode` | `EnableMirrorModeRequest` -> `EnableMirrorModeResponse` | RW | No (generic via VectorClient) |  |
| `EnableImageStreaming` | `EnableImageStreamingRequest` -> `EnableImageStreamingResponse` | RW | No (generic via VectorClient) |  |
| `IsImageStreamingEnabled` | `IsImageStreamingEnabledRequest` -> `IsImageStreamingEnabledResponse` | RO | No (generic via VectorClient) |  |
| `CancelActionByIdTag` | `CancelActionByIdTagRequest` -> `CancelActionByIdTagResponse` | RW | No (generic via VectorClient) |  |
| `CancelBehavior` | `CancelBehaviorRequest` -> `CancelBehaviorResponse` | RW | No (generic via VectorClient) |  |
| `GoToPose` | `GoToPoseRequest` -> `GoToPoseResponse` | RW | No (generic via VectorClient) |  |
| `DockWithCube` | `DockWithCubeRequest` -> `DockWithCubeResponse` | RW | No (generic via VectorClient) |  |
| `DriveOffCharger` | `DriveOffChargerRequest` -> `DriveOffChargerResponse` | RW | No (generic via VectorClient) |  |
| `DriveOnCharger` | `DriveOnChargerRequest` -> `DriveOnChargerResponse` | RW | No (generic via VectorClient) |  |
| `FindFaces` | `FindFacesRequest` -> `FindFacesResponse` | RW | No (generic via VectorClient) |  |
| `LookAroundInPlace` | `LookAroundInPlaceRequest` -> `LookAroundInPlaceResponse` | RW | No (generic via VectorClient) |  |
| `RollBlock` | `RollBlockRequest` -> `RollBlockResponse` | RW | No (generic via VectorClient) |  |
| `PhotosInfo` | `PhotosInfoRequest` -> `PhotosInfoResponse` | RO | No (generic via VectorClient) |  |
| `Photo` | `PhotoRequest` -> `PhotoResponse` | RO | No (generic via VectorClient) |  |
| `Thumbnail` | `ThumbnailRequest` -> `ThumbnailResponse` | RO | No (generic via VectorClient) |  |
| `DeletePhoto` | `DeletePhotoRequest` -> `DeletePhotoResponse` | RW | No (generic via VectorClient) |  |
| `DriveStraight` | `DriveStraightRequest` -> `DriveStraightResponse` | RW | No (generic via VectorClient) |  |
| `TurnInPlace` | `TurnInPlaceRequest` -> `TurnInPlaceResponse` | RW | No (generic via VectorClient) |  |
| `SetHeadAngle` | `SetHeadAngleRequest` -> `SetHeadAngleResponse` | RW | No (generic via VectorClient) |  |
| `SetLiftHeight` | `SetLiftHeightRequest` -> `SetLiftHeightResponse` | RW | No (generic via VectorClient) |  |
| `TurnTowardsFace` | `TurnTowardsFaceRequest` -> `TurnTowardsFaceResponse` | RW | No (generic via VectorClient) |  |
| `GoToObject` | `GoToObjectRequest` -> `GoToObjectResponse` | RW | No (generic via VectorClient) |  |
| `RollObject` | `RollObjectRequest` -> `RollObjectResponse` | RW | No (generic via VectorClient) |  |
| `PopAWheelie` | `PopAWheelieRequest` -> `PopAWheelieResponse` | RW | No (generic via VectorClient) |  |
| `PickupObject` | `PickupObjectRequest` -> `PickupObjectResponse` | RW | No (generic via VectorClient) |  |
| `PlaceObjectOnGroundHere` | `PlaceObjectOnGroundHereRequest` -> `PlaceObjectOnGroundHereResponse` | RW | No (generic via VectorClient) |  |
| `SetMasterVolume` | `MasterVolumeRequest` -> `MasterVolumeResponse` | RW | Yes (update_master_volume) |  |
| `UserAuthentication` | `UserAuthenticationRequest` -> `UserAuthenticationResponse` | RW | Yes (authenticate_robot_guid) |  |
| `BatteryState` | `BatteryStateRequest` -> `BatteryStateResponse` | RO | No (generic via VectorClient) |  |
| `VersionState` | `VersionStateRequest` -> `VersionStateResponse` | RO | No (generic via VectorClient) |  |
| `SayText` | `SayTextRequest` -> `SayTextResponse` | RW | No (generic via VectorClient) |  |
| `ConnectCube` | `ConnectCubeRequest` -> `ConnectCubeResponse` | RW | No (generic via VectorClient) |  |
| `DisconnectCube` | `DisconnectCubeRequest` -> `DisconnectCubeResponse` | RW | No (generic via VectorClient) |  |
| `CubesAvailable` | `CubesAvailableRequest` -> `CubesAvailableResponse` | RO | No (generic via VectorClient) |  |
| `FlashCubeLights` | `FlashCubeLightsRequest` -> `FlashCubeLightsResponse` | RW | No (generic via VectorClient) |  |
| `ForgetPreferredCube` | `ForgetPreferredCubeRequest` -> `ForgetPreferredCubeResponse` | RW | No (generic via VectorClient) |  |
| `SetPreferredCube` | `SetPreferredCubeRequest` -> `SetPreferredCubeResponse` | RW | No (generic via VectorClient) |  |
| `DeleteCustomObjects` | `DeleteCustomObjectsRequest` -> `DeleteCustomObjectsResponse` | RW | No (generic via VectorClient) |  |
| `CreateFixedCustomObject` | `CreateFixedCustomObjectRequest` -> `CreateFixedCustomObjectResponse` | RW | No (generic via VectorClient) |  |
| `DefineCustomObject` | `DefineCustomObjectRequest` -> `DefineCustomObjectResponse` | RW | No (generic via VectorClient) |  |
| `SetCubeLights` | `SetCubeLightsRequest` -> `SetCubeLightsResponse` | RW | No (generic via VectorClient) |  |
| `AudioFeed` | `AudioFeedRequest` -> `stream AudioFeedResponse` | Stream (RO) | No (generic via VectorClient) |  |
| `CameraFeed` | `CameraFeedRequest` -> `stream CameraFeedResponse` | Stream (RO) | Partial (extract_camera_frame helper) |  |
| `CaptureSingleImage` | `CaptureSingleImageRequest` -> `CaptureSingleImageResponse` | RO | No (generic via VectorClient) |  |
| `GetCameraConfig` | `CameraConfigRequest` -> `CameraConfigResponse` | RO | No (generic via VectorClient) |  |
| `SetEyeColor` | `SetEyeColorRequest` -> `SetEyeColorResponse` | RW | No (generic via VectorClient) |  |
| `NavMapFeed` | `NavMapFeedRequest` -> `stream NavMapFeedResponse` | Stream (RO) | No (generic via VectorClient) |  |
| `SetCameraSettings` | `SetCameraSettingsRequest` -> `SetCameraSettingsResponse` | RW | No (generic via VectorClient) |  |
| `AppIntent` | `AppIntentRequest` -> `AppIntentResponse` | RW | No (generic via VectorClient) |  |
| `UpdateSettings` | `UpdateSettingsRequest` -> `UpdateSettingsResponse` | RW | Yes (update_master_volume fallback) |  |
| `GetLatestAttentionTransfer` | `LatestAttentionTransferRequest` -> `LatestAttentionTransferResponse` | RO | No (generic via VectorClient) |  |
| `PullJdocs` | `PullJdocsRequest` -> `PullJdocsResponse` | RO | Yes (fetch_master_volume, fetch_lifetime_statistics) |  |
| `UpdateAccountSettings` | `UpdateAccountSettingsRequest` -> `UpdateAccountSettingsResponse` | RW | No (generic via VectorClient) |  |
| `StartUpdateEngine` | `CheckUpdateStatusRequest` -> `CheckUpdateStatusResponse` | RW | No (generic via VectorClient) |  |
| `CheckUpdateStatus` | `CheckUpdateStatusRequest` -> `CheckUpdateStatusResponse` | RO | No (generic via VectorClient) |  |
| `UpdateAndRestart` | `UpdateAndRestartRequest` -> `UpdateAndRestartResponse` | RW | No (generic via VectorClient) |  |
| `CheckCloudConnection` | `CheckCloudRequest` -> `CheckCloudResponse` | RO | No (generic via VectorClient) |  |
| `GetFeatureFlag` | `FeatureFlagRequest` -> `FeatureFlagResponse` | RO | No (generic via VectorClient) |  |
| `GetFeatureFlagList` | `FeatureFlagListRequest` -> `FeatureFlagListResponse` | RO | No (generic via VectorClient) |  |
| `GetAlexaAuthState` | `AlexaAuthStateRequest` -> `AlexaAuthStateResponse` | RO | No (generic via VectorClient) |  |
| `AlexaOptIn` | `AlexaOptInRequest` -> `AlexaOptInResponse` | RW | No (generic via VectorClient) |  |

## 5) Hurtigt svar paa read-only vs write

- Sensor/state/events og info-foresporgsler er `RO`.
- Koersel, animationer, settings, auth, update-kald er `RW`.
- Stream-RPC'er er markeret separat (`Stream (RO)` eller `Stream (RW)`).

## 6) Hvad er modelleret specifikt i modulet i dag

- Activity klassifikation (state->menneskevenlig tekst).
- Telemetry model (roll/pitch/yaw, lift, accel, gyro) + filtrering.
- Camera frame parsing.
- Stimulation parsing.
- Volume + lifetime-statistik wrappers.
- Provisioning/auth wrappers.

## 7) Kendte gaps

- De fleste RPC'er er tilgaengelige via generisk klient, men mangler dedikerede high-level wrappers.
- Ikke alle event payloads er endnu normaliseret til egne dataclasses.

## Kilder

- `src/pyddlvector/__init__.py`
- `src/pyddlvector/activity.py`
- `src/pyddlvector/telemetry.py`
- `src/pyddlvector/camera.py`
- `src/pyddlvector/stimulation.py`
- `src/pyddlvector/settings.py`
- `src/pyddlvector/statistics.py`
- `src/pyddlvector/provisioning.py`
- `src/pyddlvector/messaging/external_interface.proto`
- `src/pyddlvector/messaging/messages.proto`
- `src/pyddlvector/messaging/shared.proto`
- `src/pyddlvector/messaging/cube.proto`
- `src/pyddlvector/messaging/settings.proto`
