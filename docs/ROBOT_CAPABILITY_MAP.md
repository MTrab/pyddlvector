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
| `VectorClient` | class | RW | Yes | Async gRPC-klient med unary RPC, streams og BehaviorControl |
| `VectorFleet` | class | RW | Yes | Multi-robot client lifecycle |
| `RobotActivityTracker` | class | RO | Yes | Afleder user-facing activity fra events + `RobotState` |
| `describe_robot_activity` | function | RO | Yes | Direkte state->activity mapping |
| `RobotTelemetry` | dataclass | RO | Yes | Orientation/lift/IMU model |
| `TelemetryFilter` | class | RO | Yes | Rate-limit + quantization |
| `extract_robot_telemetry` | function | RO | Yes | Udtraekker telemetry fra `RobotState` |
| `CameraFrame` | dataclass | RO | Yes | Normaliseret JPEG frame |
| `extract_camera_frame` | function | RO | Yes | Parser `CameraFeedResponse` |
| `NavMapFrame` | dataclass | RO | Yes | Normaliseret PNG navmap frame |
| `NavMapRobotPose` | dataclass | RO | Yes | Normaliseret robot-pose til navmap overlay |
| `extract_nav_map_frame` | function | RO | Yes | Parser/rasterizer `NavMapFeedResponse` |
| `nav_map_robot_pose_from_state` | function | RO | Yes | Udleder navmap-kompatibel pose fra `RobotState` |
| `iter_nav_map_frames` | async generator | RO | Yes | Reconnecting `NavMapFeed` frame stream (valgfri robot-markor) |
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

### 2.5 NavMap farve-legend (human-readable)

The primary human-readable legend is documented in `README.md` under:
- `NavMap Rendering Legend`

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

Alle metoder i tabellen findes på `client.api`.

| RPC | Request -> Response | Mode | Python-metode |
|---|---|---|---|
| `ProtocolVersion` | `ProtocolVersionRequest` -> `ProtocolVersionResponse` | RO | `negotiate_protocol_version` |
| `SDKInitialization` | `SDKInitializationRequest` -> `SDKInitializationResponse` | RW | `initialize_sdk` |
| `DriveWheels` | `DriveWheelsRequest` -> `DriveWheelsResponse` | RW | `drive_wheels` |
| `PlayAnimationTrigger` | `PlayAnimationTriggerRequest` -> `PlayAnimationResponse` | RW | `play_animation_trigger` |
| `PlayAnimation` | `PlayAnimationRequest` -> `PlayAnimationResponse` | RW | `play_animation` |
| `ListAnimations` | `ListAnimationsRequest` -> `ListAnimationsResponse` | RO | `list_animations` |
| `ListAnimationTriggers` | `ListAnimationTriggersRequest` -> `ListAnimationTriggersResponse` | RO | `list_animation_triggers` |
| `MoveHead` | `MoveHeadRequest` -> `MoveHeadResponse` | RW | `move_head` |
| `MoveLift` | `MoveLiftRequest` -> `MoveLiftResponse` | RW | `move_lift` |
| `StopAllMotors` | `StopAllMotorsRequest` -> `StopAllMotorsResponse` | RW | `stop_all_motors` |
| `DisplayFaceImageRGB` | `DisplayFaceImageRGBRequest` -> `DisplayFaceImageRGBResponse` | RW | `display_rgb_face_image` |
| `EventStream` | `EventRequest` -> `stream EventResponse` | Stream (RO) | `iter_event_responses` |
| `ExternalAudioStreamPlayback` | `stream ExternalAudioStreamRequest` -> `stream ExternalAudioStreamResponse` | Stream (RW) | `open_audio_playback` |
| `BehaviorControl` | `stream BehaviorControlRequest` -> `stream BehaviorControlResponse` | Stream (RW) | `open_behavior_control` |
| `AssumeBehaviorControl` | `BehaviorControlRequest` -> `stream BehaviorControlResponse` | Stream (RW) | `assume_behavior_control` |
| `CancelFaceEnrollment` | `CancelFaceEnrollmentRequest` -> `CancelFaceEnrollmentResponse` | RW | `cancel_face_enrollment` |
| `RequestEnrolledNames` | `RequestEnrolledNamesRequest` -> `RequestEnrolledNamesResponse` | RW | `list_enrolled_faces` |
| `UpdateEnrolledFaceByID` | `UpdateEnrolledFaceByIDRequest` -> `UpdateEnrolledFaceByIDResponse` | RW | `rename_enrolled_face` |
| `EraseEnrolledFaceByID` | `EraseEnrolledFaceByIDRequest` -> `EraseEnrolledFaceByIDResponse` | RW | `erase_enrolled_face` |
| `EraseAllEnrolledFaces` | `EraseAllEnrolledFacesRequest` -> `EraseAllEnrolledFacesResponse` | RW | `erase_all_enrolled_faces` |
| `SetFaceToEnroll` | `SetFaceToEnrollRequest` -> `SetFaceToEnrollResponse` | RW | `set_face_to_enroll` |
| `EnrollFace` | `EnrollFaceRequest` -> `EnrollFaceResponse` | RW | `enroll_face` |
| `EnableMarkerDetection` | `EnableMarkerDetectionRequest` -> `EnableMarkerDetectionResponse` | RW | `enable_marker_detection` |
| `EnableFaceDetection` | `EnableFaceDetectionRequest` -> `EnableFaceDetectionResponse` | RW | `enable_face_detection` |
| `EnableMotionDetection` | `EnableMotionDetectionRequest` -> `EnableMotionDetectionResponse` | RW | `enable_motion_detection` |
| `EnableMirrorMode` | `EnableMirrorModeRequest` -> `EnableMirrorModeResponse` | RW | `enable_mirror_mode` |
| `EnableImageStreaming` | `EnableImageStreamingRequest` -> `EnableImageStreamingResponse` | RW | `enable_image_streaming` |
| `IsImageStreamingEnabled` | `IsImageStreamingEnabledRequest` -> `IsImageStreamingEnabledResponse` | RO | `get_image_streaming_status` |
| `CancelActionByIdTag` | `CancelActionByIdTagRequest` -> `CancelActionByIdTagResponse` | RW | `cancel_action_by_id` |
| `CancelBehavior` | `CancelBehaviorRequest` -> `CancelBehaviorResponse` | RW | `cancel_behavior` |
| `GoToPose` | `GoToPoseRequest` -> `GoToPoseResponse` | RW | `go_to_pose` |
| `DockWithCube` | `DockWithCubeRequest` -> `DockWithCubeResponse` | RW | `dock_with_cube` |
| `DriveOffCharger` | `DriveOffChargerRequest` -> `DriveOffChargerResponse` | RW | `drive_off_charger` |
| `DriveOnCharger` | `DriveOnChargerRequest` -> `DriveOnChargerResponse` | RW | `drive_on_charger` |
| `FindFaces` | `FindFacesRequest` -> `FindFacesResponse` | RW | `find_faces` |
| `LookAroundInPlace` | `LookAroundInPlaceRequest` -> `LookAroundInPlaceResponse` | RW | `look_around_in_place` |
| `RollBlock` | `RollBlockRequest` -> `RollBlockResponse` | RW | `roll_block` |
| `PhotosInfo` | `PhotosInfoRequest` -> `PhotosInfoResponse` | RO | `list_photos` |
| `Photo` | `PhotoRequest` -> `PhotoResponse` | RO | `get_photo` |
| `Thumbnail` | `ThumbnailRequest` -> `ThumbnailResponse` | RO | `get_photo_thumbnail` |
| `DeletePhoto` | `DeletePhotoRequest` -> `DeletePhotoResponse` | RW | `delete_photo` |
| `DriveStraight` | `DriveStraightRequest` -> `DriveStraightResponse` | RW | `drive_straight` |
| `TurnInPlace` | `TurnInPlaceRequest` -> `TurnInPlaceResponse` | RW | `turn_in_place` |
| `SetHeadAngle` | `SetHeadAngleRequest` -> `SetHeadAngleResponse` | RW | `set_head_angle` |
| `SetLiftHeight` | `SetLiftHeightRequest` -> `SetLiftHeightResponse` | RW | `set_lift_height` |
| `TurnTowardsFace` | `TurnTowardsFaceRequest` -> `TurnTowardsFaceResponse` | RW | `turn_towards_face` |
| `GoToObject` | `GoToObjectRequest` -> `GoToObjectResponse` | RW | `go_to_object` |
| `RollObject` | `RollObjectRequest` -> `RollObjectResponse` | RW | `roll_object` |
| `PopAWheelie` | `PopAWheelieRequest` -> `PopAWheelieResponse` | RW | `pop_a_wheelie` |
| `PickupObject` | `PickupObjectRequest` -> `PickupObjectResponse` | RW | `pickup_object` |
| `PlaceObjectOnGroundHere` | `PlaceObjectOnGroundHereRequest` -> `PlaceObjectOnGroundHereResponse` | RW | `place_object_on_ground_here` |
| `SetMasterVolume` | `MasterVolumeRequest` -> `MasterVolumeResponse` | RW | `set_master_volume` |
| `UserAuthentication` | `UserAuthenticationRequest` -> `UserAuthenticationResponse` | RW | `authenticate_user` |
| `BatteryState` | `BatteryStateRequest` -> `BatteryStateResponse` | RO | `get_battery_state` |
| `VersionState` | `VersionStateRequest` -> `VersionStateResponse` | RO | `get_firmware_version` |
| `SayText` | `SayTextRequest` -> `SayTextResponse` | RW | `say_text` |
| `ConnectCube` | `ConnectCubeRequest` -> `ConnectCubeResponse` | RW | `connect_cube` |
| `DisconnectCube` | `DisconnectCubeRequest` -> `DisconnectCubeResponse` | RW | `disconnect_cube` |
| `CubesAvailable` | `CubesAvailableRequest` -> `CubesAvailableResponse` | RO | `list_available_cubes` |
| `FlashCubeLights` | `FlashCubeLightsRequest` -> `FlashCubeLightsResponse` | RW | `flash_cube_lights` |
| `ForgetPreferredCube` | `ForgetPreferredCubeRequest` -> `ForgetPreferredCubeResponse` | RW | `forget_preferred_cube` |
| `SetPreferredCube` | `SetPreferredCubeRequest` -> `SetPreferredCubeResponse` | RW | `set_preferred_cube` |
| `DeleteCustomObjects` | `DeleteCustomObjectsRequest` -> `DeleteCustomObjectsResponse` | RW | `delete_custom_objects` |
| `CreateFixedCustomObject` | `CreateFixedCustomObjectRequest` -> `CreateFixedCustomObjectResponse` | RW | `create_fixed_custom_object` |
| `DefineCustomObject` | `DefineCustomObjectRequest` -> `DefineCustomObjectResponse` | RW | `define_custom_object` |
| `SetCubeLights` | `SetCubeLightsRequest` -> `SetCubeLightsResponse` | RW | `set_cube_lights` |
| `AudioFeed` | `AudioFeedRequest` -> `stream AudioFeedResponse` | Stream (RO) | `iter_audio_feed` |
| `CameraFeed` | `CameraFeedRequest` -> `stream CameraFeedResponse` | Stream (RO) | `iter_camera_feed` |
| `CaptureSingleImage` | `CaptureSingleImageRequest` -> `CaptureSingleImageResponse` | RO | `capture_single_image` |
| `GetCameraConfig` | `CameraConfigRequest` -> `CameraConfigResponse` | RO | `get_camera_config` |
| `SetEyeColor` | `SetEyeColorRequest` -> `SetEyeColorResponse` | RW | `set_eye_color` |
| `NavMapFeed` | `NavMapFeedRequest` -> `stream NavMapFeedResponse` | Stream (RO) | `iter_nav_map_feed` |
| `SetCameraSettings` | `SetCameraSettingsRequest` -> `SetCameraSettingsResponse` | RW | `set_camera_settings` |
| `AppIntent` | `AppIntentRequest` -> `AppIntentResponse` | RW | `send_app_intent` |
| `UpdateSettings` | `UpdateSettingsRequest` -> `UpdateSettingsResponse` | RW | `update_settings` |
| `GetLatestAttentionTransfer` | `LatestAttentionTransferRequest` -> `LatestAttentionTransferResponse` | RO | `get_latest_attention_transfer` |
| `PullJdocs` | `PullJdocsRequest` -> `PullJdocsResponse` | RO | `pull_jdocs` |
| `UpdateAccountSettings` | `UpdateAccountSettingsRequest` -> `UpdateAccountSettingsResponse` | RW | `update_account_settings` |
| `StartUpdateEngine` | `CheckUpdateStatusRequest` -> `CheckUpdateStatusResponse` | RW | `start_update_engine` |
| `CheckUpdateStatus` | `CheckUpdateStatusRequest` -> `CheckUpdateStatusResponse` | RO | `check_update_status` |
| `UpdateAndRestart` | `UpdateAndRestartRequest` -> `UpdateAndRestartResponse` | RW | `update_and_restart` |
| `CheckCloudConnection` | `CheckCloudRequest` -> `CheckCloudResponse` | RO | `check_cloud_connection` |
| `GetFeatureFlag` | `FeatureFlagRequest` -> `FeatureFlagResponse` | RO | `get_feature_flag` |
| `GetFeatureFlagList` | `FeatureFlagListRequest` -> `FeatureFlagListResponse` | RO | `get_feature_flag_list` |
| `GetAlexaAuthState` | `AlexaAuthStateRequest` -> `AlexaAuthStateResponse` | RO | `get_alexa_auth_state` |
| `AlexaOptIn` | `AlexaOptInRequest` -> `AlexaOptInResponse` | RW | `set_alexa_opt_in` |

## 5) Hurtigt svar paa read-only vs write

- Sensor/state/events og info-foresporgsler er `RO`.
- Koersel, animationer, settings, auth, update-kald er `RW`.
- Stream-RPC'er er markeret separat (`Stream (RO)` eller `Stream (RW)`).

## 6) Hvad er modelleret specifikt i modulet i dag

- Activity klassifikation (state->menneskevenlig tekst).
- Telemetry model (roll/pitch/yaw, lift, accel, gyro) + filtrering.
- Camera frame parsing.
- NavMap frame parsing/rasterization.
- Stimulation parsing.
- Volume + lifetime-statistik wrappers.
- Provisioning/auth wrappers.

## 7) Kendte gaps

- Understøttelsen af de enkelte RPC'er afhænger af robottens firmware.
- Ikke alle event payloads er endnu normaliseret til egne dataclasses.

## Kilder

- `src/pyddlvector/__init__.py`
- `src/pyddlvector/activity.py`
- `src/pyddlvector/telemetry.py`
- `src/pyddlvector/camera.py`
- `src/pyddlvector/navmap.py`
- `src/pyddlvector/stimulation.py`
- `src/pyddlvector/settings.py`
- `src/pyddlvector/statistics.py`
- `src/pyddlvector/provisioning.py`
- `src/pyddlvector/messaging/external_interface.proto`
- `src/pyddlvector/messaging/messages.proto`
- `src/pyddlvector/messaging/shared.proto`
- `src/pyddlvector/messaging/cube.proto`
- `src/pyddlvector/messaging/settings.proto`
