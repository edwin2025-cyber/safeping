import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";

/** A Font Awesome icon from lib/icons.js. It takes the color of the text around it.
    Sizes: 14 in tags and table cells, 16 in nav, buttons and tile labels.
    fixed: same width for every icon, so labels in a list line up.
    Decorative unless a label is given. */
export default function Icon({ icon, size = 16, fixed = false, className, label }) {
  return (
    <FontAwesomeIcon
      icon={icon}
      fixedWidth={fixed}
      className={className}
      style={{ fontSize: size }}
      aria-hidden={label ? undefined : true}
      aria-label={label}
      role={label ? "img" : undefined}
      focusable="false"
    />
  );
}
