# Episode Response Amplifier for Home Assistant

Local push integration for the Episode Response DSP amplifiers (EA-RSP-2D/8D/12D/16D). It uses the same websocket (`ws://<amp>/ws`) that the amp's own web UI uses, so no extra setup on the amp is needed.

## Install

1. Copy `custom_components/episode_rsp` into your HA `config/custom_components/` folder.
2. Restart Home Assistant.
3. Settings > Devices & services > Add integration > Episode Response Amplifier.
4. Enter the amp's IP, port 80, and the same username and password as the web UI.

## Entities

One set per stereo output zone (a 16D has 8), named from the amp:

- `media_player`: volume (0 to 100, matches the amp), mute, source select (inputs named from the amp)
- `select`: DSP preset (the amp's full preset list), config category

Zone count, names, inputs and presets are read from the amp. State is pushed by the amp, with a 60 second poll as backup and automatic reconnect.

## Notes

- The amp has no per-zone power, so zones always show as on.
- Message formats were captured from an EA-RSP-16D-100 on firmware 20211116.

## Install with HACS

1. In HACS, open the menu > Custom repositories.
2. Add `https://github.com/jeichert/episode-rsp-ha` with type **Integration**.
3. Install "Episode Response Amplifier", restart Home Assistant, then add the integration.

When a new version is published, HACS shows an update. Restart Home Assistant after updating.

## Development

`tests/mock_ws_test.py` runs the client against a mock amp (needs `aiohttp`).
