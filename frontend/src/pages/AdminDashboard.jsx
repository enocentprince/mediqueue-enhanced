import { useEffect, useState } from "react";
import { CalendarClock, ClipboardList, RefreshCw } from "lucide-react";
import {
  getAdminConsultations,
  cancelAdminAppointment,
  completeAdminAppointment,
  offerAppointmentDates,
} from "../services/api";

const baseUrl = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

function defaultOptions() {
  return ["", "", ""].map(() => ({ startsAt: "", department: "General medicine", location: "MediQueue Hospital · Block B" }));
}

export default function AdminDashboard() {
  const [consultations, setConsultations] = useState([]);
  const [options, setOptions] = useState({});
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function loadQueue() {
    setLoading(true);
    setError("");
    try {
      setConsultations(await getAdminConsultations());
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadQueue();
  }, []);

  function updateOption(consultationId, index, key, value) {
    setOptions((previous) => {
      const current = previous[consultationId] || defaultOptions();
      return {
        ...previous,
        [consultationId]: current.map((option, optionIndex) =>
          optionIndex === index ? { ...option, [key]: value } : option,
        ),
      };
    });
  }

  async function publishOptions(consultationId) {
    const selected = (options[consultationId] || defaultOptions()).filter(
      (option) => option.startsAt,
    );
    if (selected.length < 2) {
      setError("Add at least two appointment times for the patient to choose from.");
      return;
    }
    setSavingId(consultationId);
    setError("");
    setNotice("");
    try {
      await offerAppointmentDates(
        consultationId,
        selected.map((option) => ({
          starts_at: new Date(option.startsAt).toISOString(),
          department: option.department,
          location: option.location,
        })),
      );
      setNotice("Appointment options sent to the patient.");
      await loadQueue();
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setSavingId("");
    }
  }

  async function cancelAppointment(appointmentId) {
    if (!window.confirm("Cancel this patient's appointment?")) return;
    setSavingId(appointmentId);
    setError("");
    setNotice("");
    try {
      await cancelAdminAppointment(appointmentId);
      setNotice("Appointment cancelled.");
      await loadQueue();
    } catch (cancelError) {
      setError(cancelError.message);
    } finally {
      setSavingId("");
    }
  }

  async function completeAppointment(appointmentId) {
    setSavingId(appointmentId);
    setError("");
    setNotice("");
    try {
      await completeAdminAppointment(appointmentId);
      setNotice("Appointment marked as completed.");
      await loadQueue();
    } catch (completeError) {
      setError(completeError.message);
    } finally {
      setSavingId("");
    }
  }

  return (
    <main className="container admin-workspace">
      <div className="admin-heading">
        <div>
          <span className="eyebrow plain">CARE TEAM WORKSPACE</span>
          <h1>Consultation review</h1>
          <p className="page-intro">
            Review patient-submitted concerns and offer appointment times for them to select.
          </p>
        </div>
        <button className="button button-outline refresh-button" onClick={loadQueue} disabled={loading}>
          <RefreshCw size={16} /> Refresh
        </button>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {notice && <p className="success-message" role="status">{notice}</p>}
      {loading ? (
        <p role="status">Loading consultations...</p>
      ) : consultations.length === 0 ? (
        <section className="panel empty-appointment">
          <ClipboardList size={38} />
          <h2>No consultations to review</h2>
          <p>Submitted patient pre-consultations will appear here.</p>
        </section>
      ) : (
        <div className="admin-queue">
          {consultations.map((consultation) => {
            const offered = consultation.offers.some((offer) => offer.status === "offered");
            const selected = consultation.offers.find((offer) => offer.status === "selected");
            const appointment = consultation.appointment;
            const activeAppointment =
              appointment &&
              ["confirmed", "reschedule_requested"].includes(appointment.status);
            const canComplete =
              appointment?.status === "confirmed" &&
              new Date(appointment.starts_at) <= new Date();
            const currentOptions = options[consultation.id] || defaultOptions();
            return (
              <article className="admin-consultation" key={consultation.id}>
                <header className="admin-patient-heading">
                  <div>
                    <h2>{consultation.patient.name}</h2>
                    <p>{consultation.patient.email} · Submitted {new Date(`${consultation.created_at}Z`).toLocaleString()}</p>
                  </div>
                  <span className="admin-status">
                    {activeAppointment
                      ? appointment.status === "reschedule_requested"
                        ? "Reschedule requested"
                        : appointment.status === "completed"
                          ? "Appointment completed"
                          : "Appointment confirmed"
                      : appointment
                        ? appointment.status === "completed"
                          ? "Appointment completed"
                          : "Appointment cancelled"
                        : selected
                          ? "Appointment selected"
                          : offered
                            ? "Options sent"
                            : "Needs review"}
                  </span>
                </header>
                <div className="admin-health-grid">
                  <div><strong>Reported concerns</strong><p>{consultation.symptoms.join(", ") || "Not provided"}</p></div>
                  <div><strong>Started</strong><p>{consultation.duration || "Not provided"}</p></div>
                  <div><strong>Daily impact</strong><p>{consultation.impact || "Not provided"}</p></div>
                  <div><strong>Conditions & allergies</strong><p>{consultation.history || "Not provided"}</p></div>
                  <div><strong>Current medicines</strong><p>{consultation.medicines || "Not provided"}</p></div>
                  <div><strong>Additional notes</strong><p>{consultation.notes || "Not provided"}</p></div>
                </div>
                {consultation.images.length > 0 && (
                  <div className="admin-images">
                    <strong>Patient photos</strong>
                    <div>
                      {consultation.images.map((image) => (
                        <a
                          key={image.id}
                          href={`${baseUrl}/admin/consultations/${consultation.id}/images/${image.id}`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {image.filename}
                        </a>
                      ))}
                    </div>
                  </div>
                )}
                {consultation.offers.length > 0 && (
                  <div className="published-offers">
                    <strong>Appointment options and history</strong>
                    {consultation.offers.map((offer) => (
                      <span key={offer.id}>
                        {new Date(offer.starts_at).toLocaleString()} · {offer.status}
                      </span>
                    ))}
                  </div>
                )}
                {activeAppointment && (
                  <section className="admin-current-appointment">
                    <div>
                      <strong>Current appointment</strong>
                      <p>
                        {new Date(appointment.starts_at).toLocaleString()} · {appointment.department} · {appointment.location}
                      </p>
                    </div>
                    <button
                      className="button button-outline cancel-appointment-button"
                      type="button"
                      disabled={savingId === appointment.id}
                      onClick={() => cancelAppointment(appointment.id)}
                    >
                      {savingId === appointment.id ? "Cancelling..." : "Cancel appointment"}
                    </button>
                    {canComplete && (
                      <button
                        className="button button-outline"
                        type="button"
                        disabled={savingId === appointment.id}
                        onClick={() => completeAppointment(appointment.id)}
                      >
                        {savingId === appointment.id
                          ? "Saving..."
                          : "Mark as completed"}
                      </button>
                    )}
                  </section>
                )}
                {selected && !appointment && (
                  <p className="success-message">
                    Patient chose {new Date(selected.starts_at).toLocaleString()}.
                  </p>
                )}
                {!appointment || activeAppointment ? <section className="offer-editor">
                  <h3>
                    <CalendarClock size={18} />
                    {activeAppointment ? "Offer replacement times" : "Offer appointment options"}
                  </h3>
                  {activeAppointment && (
                    <p className="muted">
                      The current booking remains in place until the patient chooses a replacement time.
                    </p>
                  )}
                  {offered && <p className="muted">New options replace any times the patient has not chosen yet.</p>}
                  <div className="offer-options-grid">
                    {currentOptions.map((option, index) => (
                      <label className="register-field" key={index}>
                        <span>Option {index + 1}</span>
                        <input
                          aria-label={`Appointment option ${index + 1} for ${consultation.patient.name}`}
                          type="datetime-local"
                          value={option.startsAt}
                          onChange={(event) => updateOption(consultation.id, index, "startsAt", event.target.value)}
                        />
                      </label>
                    ))}
                  </div>
                  <button
                    className="button button-primary"
                    type="button"
                    disabled={savingId === consultation.id}
                    onClick={() => publishOptions(consultation.id)}
                  >
                    {savingId === consultation.id
                      ? "Sending options..."
                      : activeAppointment
                        ? "Send replacement times"
                        : "Send dates to patient"}
                  </button>
                </section> : null}
              </article>
            );
          })}
        </div>
      )}
    </main>
  );
}