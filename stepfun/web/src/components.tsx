import type { ReactNode } from "react";

export type NotifyKind = "info" | "success" | "error";
export type Notify = (text: string, kind?: NotifyKind) => void;

export function Card({
  title,
  subtitle,
  actions,
  children,
  className = "",
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-head">
          <div>
            {title && <h2>{title}</h2>}
            {subtitle && <p className="card-sub">{subtitle}</p>}
          </div>
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function Chip({
  children,
  tone = "neutral",
  title,
}: {
  children: ReactNode;
  tone?: "neutral" | "good" | "warn" | "bad" | "accent";
  title?: string;
}) {
  return (
    <span className={`chip chip-${tone}`} title={title}>
      {children}
    </span>
  );
}

export function Progress({ value, label }: { value: number; label?: string }) {
  const ratio = Math.max(0, Math.min(1, value));
  return (
    <div className="progress-wrap">
      <div className="progress">
        <div className="progress-fill" style={{ width: `${ratio * 100}%` }} />
      </div>
      <div className="progress-label">
        <span>{label ?? ""}</span>
        <span>{Math.round(ratio * 100)}%</span>
      </div>
    </div>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

export function Empty({ title, hint }: { title: string; hint?: ReactNode }) {
  return (
    <div className="empty">
      <div className="empty-mark">◌</div>
      <div className="empty-title">{title}</div>
      {hint && <div className="empty-hint">{hint}</div>}
    </div>
  );
}
