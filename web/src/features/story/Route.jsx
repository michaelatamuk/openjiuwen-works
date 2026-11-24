import { useLayoutEffect, useRef, useState } from "react";
import { timeAgo } from "../../lib/format.js";
import { milestoneCopy } from "./copy.js";
import { ROUTE_X0, ROUTE_X1, lengthAtX, routeYAt, smoothPath } from "./route.js";

function Route({ stages, selected, onSelect, taskState, detail }) {
  const progressRef = useRef(null);
  const [points, setPoints] = useState([]);
  const activeIndex = Math.max(0, stages.findIndex((stage) =>
    ["active", "blocked"].includes(stage.state)
  ));
  const effectiveIndex = stages.some((stage) => ["active", "blocked"].includes(stage.state))
    ? activeIndex
    : Math.max(0, stages.map((stage) => stage.state).lastIndexOf("done"));
  const routePoints = stages.map((_, index) => ({
    x: ROUTE_X0 + (ROUTE_X1 - ROUTE_X0) * (index / Math.max(1, stages.length - 1)),
    y: routeYAt(index, stages.length),
  }));
  const routeD = smoothPath(routePoints);
  const baseD = smoothPath(routePoints.slice(1));
  const intakeD = routePoints.length > 1
    ? `M ${routePoints[0].x} ${routePoints[0].y} C ${routePoints[0].x + 60} ${routePoints[0].y - 45} ${routePoints[1].x - 55} ${routePoints[0].y + 18} ${routePoints[1].x} ${routePoints[1].y}`
    : "";

  useLayoutEffect(() => {
    const path = progressRef.current;
    if (!path || !stages.length) return;
    const length = path.getTotalLength();
    const next = stages.map((stage, index) => {
      const point = routePoints[index];
      return {
        stage,
        display: index === 0 ? "source" : stage.state || "pending",
        side: index % 2 === 0 ? "above" : "below",
        point,
      };
    });
    setPoints(next);
    const progress = progressRef.current;
    if (progress) {
      const stageLengths = next.map(({ point }) => lengthAtX(path, point.x));
      const start = stageLengths[1] ?? 0;
      const end = stageLengths[effectiveIndex] ?? start;
      progress.style.strokeDasharray = `${Math.max(0, end - start)} ${length}`;
      progress.style.strokeDashoffset = `${-start}`;
      progress.classList.toggle("blocked", stages[effectiveIndex]?.state === "blocked");
    }
  }, [stages, effectiveIndex]);

  const activePoint = points[effectiveIndex]?.point;
  const showMira = taskState !== "queued" && effectiveIndex > 0 && Boolean(activePoint);
  const node = (display, kind) =>
    display === "done" ? "✓" : display === "blocked" ? "!" : display === "active" ? (kind === "gate" ? "◆" : "•") : "";

  return (
    <section className="route-block" aria-label="Fix route">
      <div className="route-head">
        <span className="route-title">The fix route</span>
        <span className="route-legend">
          <span><i className="legend-dot origin" />Origin</span>
          <span><i className="legend-dot pending" />Not started</span>
          <span><i className="legend-dot active" />Mira is here</span>
          <span><i className="legend-dot waiting" />Waits for you</span>
          <span><i className="legend-dot done" />Done</span>
          <span><i className="legend-dot blocked" />Stopped</span>
        </span>
      </div>
      <div className="route-scroll">
        <div className="route-wrap">
          <svg className="route-svg" viewBox="0 0 1200 380" preserveAspectRatio="none" aria-hidden="true">
            <path className="route-base" d={baseD} />
            <path className="route-intake" d={intakeD} />
            <path ref={progressRef} className="route-progress" d={routeD} />
          </svg>
          <div className="route-points" role="list" aria-label="Fix milestones">
            {points.map(({ stage, display, side, point }, index) => {
              const copy = display === "source" ? "Reported" : milestoneCopy(stage, display, detail);
              return (
                <div
                  key={stage.id}
                  className={`milestone ${display} ${side}${stage.kind === "gate" ? " gate" : ""}${stage.id === selected ? " selected" : ""}`}
                  style={{ left: `${(point.x / 1200) * 100}%`, top: `${(point.y / 380) * 100}%` }}
                  role="listitem"
                  aria-label={`${copy}, ${display === "source" ? "origin" : display}${stage.at ? `, ${timeAgo(stage.at)}` : ""}`}
                  aria-current={display === "active" ? "step" : undefined}
                  onClick={() => onSelect(stage.id)}
                >
                  <span className="m-node" aria-hidden="true">{node(display, stage.kind)}</span>
                  <span className="m-copy">
                    <strong>{copy}</strong>
                    {stage.at && display !== "pending" ? (
                      <em>
                        {display === "source"
                          ? `from ${detail.task.source.ref} · ${timeAgo(stage.at)}`
                          : timeAgo(stage.at)}
                      </em>
                    ) : null}
                  </span>
                </div>
              );
            })}
          </div>
          <div
            className={`route-mira${effectiveIndex % 2 === 1 ? " above-node" : ""}${effectiveIndex === stages.length - 1 ? " finish" : ""}`}
            style={activePoint ? { left: `${(activePoint.x / 1200) * 100}%`, top: `${(activePoint.y / 380) * 100}%` } : { display: "none" }}
            hidden={!showMira}
            aria-hidden="true"
          >
            <img src="/mira.svg" alt="" width="52" height="52" />
          </div>
        </div>
      </div>
    </section>
  );
}

export { Route };
