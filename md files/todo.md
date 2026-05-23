# TODO

## Route Finder Next Steps

- Add OpenRouteService routing provider for the current Yelp/US dataset.
  - Implement `OpenRouteServiceDirectionClient` for walking, driving, and cycling directions.
  - Normalize ORS responses into the existing `RouteLeg` schema: distance, duration, provider status, and polyline.
  - Keep the current PyDeck debug map unchanged and draw ORS route polylines through the existing route layer.

- Add route provider controls.
  - Use OpenRouteService as the only route provider.
  - Surface ORS provider errors clearly in route warnings, including quota and out-of-coverage failures.

- Add geocoding for user-entered anchors and return locations.
  - Prefer OpenRouteService Geocode API if ORS is already configured.
  - Optionally support Nominatim for low-volume local debugging.
  - Convert text like hotel names, neighborhoods, and return locations into coordinates before route generation.
  - Cache geocoding results under `cache/geocoding/` to avoid repeated provider calls.

- Add provider configuration.
  - Add `OPENROUTESERVICE_API_KEY` and `ORS_TIMEOUT_SEC` to `.env.local`.
  - Validate missing/invalid provider keys before route generation.

- Improve route candidate generation.
  - Keep the current one-POI-per-event behavior as the default.
  - Add an option for multiple POIs per event when the user wants a denser itinerary.
  - Add route diversity so top candidates do not all reuse the same top POI.
  - Add configurable limits for provider calls to avoid quota bursts.

- Add fallback routing.
  - If a provider returns out-of-service, estimate distance/time with haversine distance and mode-specific speeds.
  - Mark fallback legs as approximate, not provider-verified.
  - Rank verified routes above approximate routes when scores are otherwise close.

- Add time-window planning.
  - Use parsed `start_time`, `end_time`, dwell minutes, and return requirement to reject impossible routes.
  - Show arrival/departure estimates per stop.
  - Add explicit warnings for routes that cannot return before the user deadline.

- Add tests.
  - Mock ORS success/failure responses.
  - Test provider auto-selection for China vs non-China coordinates.
  - Test geocoding cache hits and misses.
  - Test fallback estimated legs after provider out-of-coverage errors.
  - Test route diversity and provider-call caps.
