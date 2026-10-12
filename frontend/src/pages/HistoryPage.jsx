import { useEffect, useState } from "react";
import { CalendarDays, Clock3, MapPin, Building2 } from "lucide-react";
import Button from "../components/Button";
import { getAppointments } from "../services/api";

export default function HistoryPage({ demo, onStartNewConsultation }) {
  const [appointments, setAppointments] = useState([]);
  const [loading, setLoading] = useState(!demo);
  const [error, setError] = useState("");

  useEffect(() => {
    if (demo) return;
    getAppointments()
      .then(setAppointments)
      .catch((loadError) => setError(loadError.message))
      .finally(() => setLoading(false));
  }, [demo]);

  const history = appointments
    .filter((appointment) =>
      ["completed", "cancelled"].includes(appointment.status),
    )
    .sort((first, second) => second.starts_at.localeCompare(first.starts_at));

  return (
    <main className="container workspace history-page">
      <span className="eyebrow plain">YOUR PATIENT SPACE</span>
      <h1>History</h1>
      <p className="page-intro">
        Completed and cancelled appointments from your previous visits.
      </p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {loading ? (
        <section className="panel empty-appointment" role="status">
          <CalendarDays size={38} />
          <h2>Loading your history</h2>
        </section>
      ) : history.length ? (
        <div className="history-list">
          {history.map((appointment) => (
            <article className="panel history-appointment" key={appointment.id}>
              <div className="history-appointment-heading">
                <h2>
                  {appointment.status === "completed"
                    ? "Completed appointment"
                    : "Cancelled appointment"}
                </h2>
                <span className={`history-status ${appointment.status}`}>
                  {appointment.status}
                </span>
              </div>
              <div className="history-details">
                <span>
                  <CalendarDays size={17} />
                  {new Date(appointment.starts_at).toLocaleDateString()}
                </span>
                <span>
                  <Clock3 size={17} />
                  {new Date(appointment.starts_at).toLocaleTimeString([], {
                    hour: "numeric",
                    minute: "2-digit",
                  })}
                </span>
                <span>
                  <Building2 size={17} />
                  {appointment.department}
                </span>
                <span>
                  <MapPin size={17} />
                  {appointment.location}
                </span>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <section className="panel empty-appointment">
          <CalendarDays size={38} />
          <h2>No appointment history yet</h2>
          <p>Completed or cancelled appointments will appear here.</p>
        </section>
      )}
      <div className="history-actions">
        <Button onClick={onStartNewConsultation}>
          Start a new pre-consultation
        </Button>
        <Button variant="outline" href="#/dashboard">
          Back to my dashboard
        </Button>
      </div>
    </main>
  );
}
