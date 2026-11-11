// Every icon in the dashboard, in one place. Font Awesome 6 Free, solid style
// (fontawesome.com, CC BY 4.0). Import icons by name only, so the build keeps
// just the ones used here. To change an icon, change one line in this map.
import { config } from "@fortawesome/fontawesome-svg-core";
import {
  faAnglesLeft,
  faAnglesRight,
  faArrowDown,
  faArrowDownWideShort,
  faArrowUp,
  faArrowUpRightFromSquare,
  faBan,
  faBatteryEmpty,
  faBatteryFull,
  faBatteryHalf,
  faBatteryQuarter,
  faBatteryThreeQuarters,
  faBell,
  faBellSlash,
  faBuilding,
  faBullseye,
  faCalendarDay,
  faCalendarDays,
  faChartSimple,
  faCheck,
  faChevronDown,
  faChevronLeft,
  faChevronRight,
  faCircleCheck,
  faCircleDot,
  faCircleExclamation,
  faCircleHalfStroke,
  faCircleInfo,
  faCircleQuestion,
  faClock,
  faClockRotateLeft,
  faClone,
  faCopy,
  faDownload,
  faExpand,
  faEye,
  faFileCsv,
  faFileExcel,
  faFilter,
  faFire,
  faGauge,
  faGear,
  faHashtag,
  faHeartCircleCheck,
  faHeartPulse,
  faHourglassHalf,
  faInbox,
  faLayerGroup,
  faList,
  faLocationCrosshairs,
  faLocationDot,
  faMagnifyingGlass,
  faMap,
  faMessage,
  faMicrochip,
  faMinus,
  faPlus,
  faPowerOff,
  faRightFromBracket,
  faShieldHalved,
  faStopwatch,
  faTableColumns,
  faTemperatureHalf,
  faTowerBroadcast,
  faTriangleExclamation,
  faUpRightAndDownLeftFromCenter,
  faUpRightFromSquare,
  faUser,
  faVideo,
  faVolumeHigh,
  faWifi,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";

// The Font Awesome CSS is imported once in main.jsx, so do not inject it again at run time.
config.autoAddCss = false;

export const icons = {
  // App and navigation
  app: faShieldHalved,
  overview: faChartSimple,
  live: faTowerBroadcast,
  devices: faMicrochip,
  settings: faGear,
  search: faMagnifyingGlass,
  student: faUser,
  filter: faFilter,
  sort: faArrowDownWideShort,
  collapse: faAnglesLeft,
  expand: faAnglesRight,
  chevronDown: faChevronDown,
  chevronLeft: faChevronLeft,
  chevronRight: faChevronRight,
  calendar: faCalendarDays,
  logOut: faRightFromBracket,

  // Alert types
  medical: faHeartPulse,
  suspicious: faEye,
  silent: faBellSlash,
  status: faCircleCheck,
  unknownType: faCircleQuestion,

  // Alert states and actions
  open: faCircleDot,
  acknowledged: faCheck,
  resolve: faCircleCheck,
  copy: faCopy,
  download: faDownload,
  excel: faFileExcel,
  csv: faFileCsv,
  close: faXmark,
  openFullPage: faUpRightAndDownLeftFromCenter,
  externalLink: faArrowUpRightFromSquare,
  openRow: faUpRightFromSquare,

  // Links
  lora: faTowerBroadcast,
  wifi: faWifi,

  // Properties
  time: faClock,
  messageNumber: faHashtag,
  place: faLocationDot,
  gps: faLocationDot,
  floor: faBuilding,
  camera: faVideo,
  pressure: faGauge,
  temperature: faTemperatureHalf,
  text: faMessage,
  area: faBullseye,
  history: faClockRotateLeft,
  late: faHourglassHalf,
  boot: faPowerOff,

  // Map
  zoomIn: faPlus,
  zoomOut: faMinus,
  fitAll: faExpand,
  center: faLocationCrosshairs,
  mapLabels: faLayerGroup,

  // Live views and empty states
  split: faTableColumns,
  list: faList,
  map: faMap,
  inbox: faInbox,

  // Overview and system health
  alerts: faBell,
  medianAck: faStopwatch,
  openNow: faCircleExclamation,
  urgent: faTriangleExclamation,
  lastAlert: faClock,
  today: faCalendarDay,
  activity: faClockRotateLeft,
  fobsActive: faMicrochip,
  lowBattery: faBatteryQuarter,
  warning: faTriangleExclamation,
  rejected: faBan,
  duplicates: faClone,
  hotspots: faFire,
  health: faHeartCircleCheck,
  up: faArrowUp,
  down: faArrowDown,
  chart: faChartSimple,

  // Settings
  theme: faCircleHalfStroke,
  bell: faBell,
  info: faCircleInfo,
  sound: faVolumeHigh,
};

/** Battery icon for a percent: full, three quarters, half, quarter or empty. */
export function batteryIcon(pct) {
  if (pct === null || pct === undefined) return faBatteryHalf;
  if (pct >= 88) return faBatteryFull;
  if (pct >= 63) return faBatteryThreeQuarters;
  if (pct >= 38) return faBatteryHalf;
  if (pct >= 10) return faBatteryQuarter;
  return faBatteryEmpty;
}
