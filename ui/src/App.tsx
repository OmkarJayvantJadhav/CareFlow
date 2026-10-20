import { Navigate, Route, Routes } from "react-router-dom";
import type { Role } from "./api";
import Layout from "./components/Layout";
import Analytics from "./pages/Analytics";
import Appointments from "./pages/Appointments";
import Chat from "./pages/Chat";
import Dashboard from "./pages/Dashboard";
import DoctorStatus from "./pages/DoctorStatus";
import FrontDesk from "./pages/FrontDesk";
import QueueStatus from "./pages/QueueStatus";
import Start from "./pages/Start";
import { useSession } from "./session";

export const HOME: Record<Role, string> = {
  patient: "/chat",
  caregiver: "/chat",
  staff: "/desk",
  admin: "/admin",
};

function Guard({ roles, children }: { roles: Role[]; children: JSX.Element }) {
  const { user } = useSession();
  if (!user) return <Navigate to="/" replace />;
  if (!roles.includes(user.role)) return <Navigate to={HOME[user.role]} replace />;
  return children;
}

export default function App() {
  const patientRoles: Role[] = ["patient", "caregiver"];
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Start />} />
        <Route path="/chat" element={<Guard roles={patientRoles}><Chat /></Guard>} />
        <Route path="/appointments" element={<Guard roles={patientRoles}><Appointments /></Guard>} />
        <Route path="/queue" element={<Guard roles={patientRoles}><QueueStatus /></Guard>} />
        <Route path="/desk" element={<Guard roles={["staff"]}><FrontDesk /></Guard>} />
        <Route path="/doctors" element={<Guard roles={["staff"]}><DoctorStatus /></Guard>} />
        <Route path="/admin" element={<Guard roles={["admin"]}><Dashboard /></Guard>} />
        <Route path="/analytics" element={<Guard roles={["admin"]}><Analytics /></Guard>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
