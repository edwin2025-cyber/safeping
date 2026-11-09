// Fake data for mock mode (npm run dev:mock). Every name here is made up.
// Times are minutes before the page loaded, so the data always looks recent.

export const MOCK_CONFIG = {
  carto_key: null, // always null: the map uses OpenStreetMap tiles
  pa_per_floor: 42,
  ref_max_age_s: 120,
  defaults: { sight_radius_m: 50, camera_before_min: 2, camera_after_min: 5 },
  version: "mock",
  commit: null,
};

// Near the demo coordinates in docs/dashboard.md (34.7304, -86.5861).
export const MOCK_PLACES = [
  { name: "the Mockingbird Hall entrance", lat: 34.7304, lon: -86.5861 },
  { name: "the pretend bus loop", lat: 34.7318, lon: -86.5842 },
  { name: "the sample practice field", lat: 34.7289, lon: -86.5879 },
  { name: "the demo gym doors", lat: 34.7296, lon: -86.5838 },
];

export const MOCK_PLACES_MAX_DISTANCE_M = 200;

export const MOCK_DEVICES = [
  { device_id: "MOCK-FOB-01", role: "FOB", student_name: "Mock Student Alpha", battery: 92 },
  { device_id: "MOCK-FOB-02", role: "FOB", student_name: "Mock Student Bravo", battery: 64 },
  { device_id: "MOCK-FOB-03", role: "FOB", student_name: "Mock Student Charlie", battery: 31 },
  { device_id: "MOCK-FOB-04", role: "FOB", student_name: "Mock Student Delta", battery: 8 },
];

export const MOCK_STATUS = {
  reference_pressure: 101300,
  reference_age_s: 20,
  rejected_total: 0,
};

// The two at 34.7317, -86.5843 sit on the same spot, so the map shows a cluster.
// state: "open", "acknowledged" or "resolved".
export const MOCK_ALERTS = [
  { device: "MOCK-FOB-01", type: "MEDICAL", state: "open", minAgo: 2, link: "lora", lat: 34.7317, lon: -86.5843, acc: 8 },
  { device: "MOCK-FOB-02", type: "SUSPICIOUS", state: "open", minAgo: 4, link: "wifi", lat: 34.7317, lon: -86.5843, acc: 12 },
  { device: "MOCK-FOB-03", type: "SILENT", state: "open", minAgo: 6, link: "lora", floor: 3 },
  { device: "MOCK-FOB-03", type: "STATUS", state: "open", minAgo: 10, link: "wifi", lat: 34.7262, lon: -86.5911, acc: 15 },
  { device: "MOCK-FOB-04", type: "MEDICAL", state: "acknowledged", minAgo: 15, link: "lora", lat: 34.7298, lon: -86.5836, acc: 6 },
  { device: "MOCK-FOB-01", type: "SUSPICIOUS", state: "acknowledged", minAgo: 25, link: "wifi", floor: 2 },
  { device: "MOCK-FOB-02", type: "SILENT", state: "resolved", minAgo: 120, link: "lora", lat: 34.7286, lon: -86.5884, acc: 10 },
  { device: "MOCK-FOB-04", type: "MEDICAL", state: "resolved", minAgo: 180, link: "unknown" },
];
