import { useLayoutEffect, useRef } from "react";

/** A table's scrolling container. On a phone each row becomes a card (styles.css, `.stack-on-phone`), so every
 * cell is labelled with its column's heading here; a column whose heading is only for screen readers (such as
 * the actions column) gets no label. */
export default function TableWrap({ className = "", children, ...rest }) {
  const ref = useRef(null);
  useLayoutEffect(() => {
    for (const table of ref.current?.querySelectorAll("table") ?? []) {
      const heads = [...table.querySelectorAll("thead th")].map((th) => {
        const hidden = th.children.length === 1 && th.firstElementChild.classList.contains("sr-only");
        return hidden ? "" : th.textContent.trim();
      });
      for (const row of table.querySelectorAll("tbody tr")) {
        [...row.children].forEach((cell, i) => {
          if (cell.tagName === "TD" && heads[i]) cell.dataset.label = heads[i];
          else delete cell.dataset.label;
        });
      }
    }
  });
  return (
    <div ref={ref} className={`table-wrap stack-on-phone ${className}`.trim()} {...rest}>
      {children}
    </div>
  );
}
