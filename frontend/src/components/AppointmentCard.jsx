import { useState } from "react";
import { CalendarDays, Clock3, MapPin, Building2, Check } from "lucide-react";
export default function AppointmentCard({
  compact = false,
  appointment,
  demo = false,
  offerCount = 0,
  onCancel,
  onRequestReschedule,
}) {
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  if (!appointment && !demo) return null;
  async function runAction(action) {
    setActionError("");
    if (action === onCancel && !window.confirm("Cancel this appointment?")) return;
    setBusy(true);
    try {
      await action();
    } catch (error) {
      setActionError(error.message);
    } finally {
      setBusy(false);
    }
  }
  const details = appointment
    ? [
        [
          CalendarDays,
          "Date",
          new Date(appointment.starts_at).toLocaleDateString(),
        ],
        [
          Clock3,
          "Time",
          new Date(appointment.starts_at).toLocaleTimeString([], {
            hour: "numeric",
            minute: "2-digit",
          }),
        ],
        [Building2, "Department", appointment.department],
        [MapPin, "Location", appointment.location],
      ]
    : [
        [CalendarDays, "Date", "Tuesday, 20 October"],
        [Clock3, "Time", "10:30 AM"],
        [Building2, "Department", "General medicine"],
        [MapPin, "Location", "Demo Hospital · Block B"],
      ];
  return (
    <div className={`appointment-card ${compact ? "compact" : ""}`}>
      <div className="appointment-status">
        <span className="check-circle">
          <Check size={compact ? 19 : 26} />
        </span>
        <strong>
          {appointment
            ? appointment.status === "cancelled"
              ? "Your appointment was cancelled"
              : appointment.status === "completed"
                ? "Your appointment has been completed"
                : "Your appointment is confirmed"
            : compact
              ? "Your visit, planned."
              : "Your sample appointment"}
        </strong>
        <span className="muted">
          {compact
            ? "A little less waiting."
            : appointment
              ? appointment.status === "reschedule_requested"
                ? "Your care team is arranging a new time. Your current booking is held until you choose a replacement."
                : appointment.status === "cancelled"
                  ? "This appointment is no longer active."
                  : appointment.status === "completed"
                    ? "This visit is complete. You can start a new pre-consultation for another appointment."
                  : "Your care team has your pre-consultation."
              : "Demo only · no appointment has been booked"}
        </span>
      </div>
      <div className="appointment-details">
        {details.map(([Icon, label, value]) => (
          <div className="detail-row" key={label}>
            <span className="detail-icon">
              <Icon size={18} />
            </span>
            <div>
              <small>{label}</small>
              <strong>{value}</strong>
            </div>
          </div>
        ))}
      </div>
      <p className="appointment-note">
        {appointment?.status === "cancelled"
          ? "Contact your care team if you need help arranging another visit."
          : appointment?.status === "completed"
            ? "You can review this visit in your appointment history."
            : "Please arrive 10 minutes before your scheduled time."}
      </p>
      {appointment?.status === "confirmed" && (onCancel || onRequestReschedule) && (
        <div className="appointment-actions">
          {onRequestReschedule && (
            <button
              className="button button-outline"
              type="button"
              disabled={busy}
              onClick={() => runAction(onRequestReschedule)}
            >
              Request a new time
            </button>
          )}
          {onCancel && (
            <button
              className="button button-outline cancel-appointment-button"
              type="button"
              disabled={busy}
              onClick={() => runAction(onCancel)}
            >
              Cancel appointment
            </button>
          )}
        </div>
      )}
      {appointment?.status === "reschedule_requested" && (
        <div className="appointment-actions">
          <a className="button button-primary" href="#/appointment">
            {offerCount > 0 ? "Choose a new time" : "Check for new times"}
          </a>
          {offerCount === 0 && (
            <span className="muted">Your current booking stays in place.</span>
          )}
          {onCancel && (
            <button
              className="button button-outline cancel-appointment-button"
              type="button"
              disabled={busy}
              onClick={() => runAction(onCancel)}
            >
              Cancel appointment
            </button>
          )}
        </div>
      )}
      {actionError && <p className="error" role="alert">{actionError}</p>}
    </div>
  );
}
