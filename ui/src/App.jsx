import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import Layout from "./components/Layout";
import Account from "./pages/Account";
import Accounts from "./pages/Accounts";
import Analytics from "./pages/Analytics";
import Documents from "./pages/Documents";
import Home from "./pages/Home";
import Messaging from "./pages/Messaging";
import HospitalSetup from "./pages/HospitalSetup";
import Appointments from "./pages/Appointments";
import Book from "./pages/Book";
import Calendar from "./pages/Calendar";
import Chat from "./pages/Chat";
import Coordination from "./pages/Coordination";
import Dashboard from "./pages/Dashboard";
import DoctorQueue from "./pages/DoctorQueue";
import DoctorStatus from "./pages/DoctorStatus";
import FrontDesk from "./pages/FrontDesk";
import Kiosk from "./pages/Kiosk";
import Library from "./pages/Library";
import LibraryDoc from "./pages/LibraryDoc";
import Notifications from "./pages/Notifications";
import PriorityRules from "./pages/PriorityRules";
import Patients from "./pages/Patients";
import Profile from "./pages/Profile";
import QueueStatus from "./pages/QueueStatus";
import Receipt from "./pages/Receipt";
import RegistrationForm from "./pages/RegistrationForm";
import Start from "./pages/Start";
import { useSession } from "./session";

export const HOME = {
  patient: "/chat",
  caregiver: "/chat",
  staff: "/desk",
  admin: "/admin",
  doctor: "/my-queue",
};

/** `fullScreen` pages sit outside the layout, which is where a temporary password must be replaced first. */
function Guard({ roles, fullScreen = false, children }) {
  const { user, demo } = useSession();
  const location = useLocation();
  // A hospital's deployment sends visitors to log in and back here afterwards; the demo has its roles on "/".
  if (!user)
    return demo ? <Navigate to="/" replace /> : <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (fullScreen && user.must_change_password) return <Navigate to={HOME[user.role]} replace />;
  if (!roles.includes(user.role)) return <Navigate to={HOME[user.role]} replace />;
  return children;
}

/** "/": a hospital's own deployment shows its homepage to visitors (D-134); the demo keeps its start page. */
export function Root() {
  const { user, config, demo } = useSession();
  if (config === null) return null; // until /config answers
  return demo || user ? <Start /> : <Home />;
}

export default function App() {
  const patientRoles = ["patient", "caregiver"];
  return (
    <Routes>
      {/* The kiosk is full screen, without the app's navigation (feature 27). */}
      <Route
        path="/kiosk"
        element={
          <Guard roles={["staff"]} fullScreen>
            <Kiosk />
          </Guard>
        }
      />
      <Route element={<Layout />}>
        <Route path="/" element={<Root />} />
        <Route path="/login" element={<Start />} />
        {/* Hospital information: open to everyone, signed in or not. */}
        <Route path="/library" element={<Library />} />
        <Route path="/library/:collection/:slug" element={<LibraryDoc />} />
        <Route
          path="/chat"
          element={
            <Guard roles={patientRoles}>
              <Chat />
            </Guard>
          }
        />
        <Route
          path="/appointments"
          element={
            <Guard roles={patientRoles}>
              <Appointments />
            </Guard>
          }
        />
        <Route
          path="/queue"
          element={
            <Guard roles={patientRoles}>
              <QueueStatus />
            </Guard>
          }
        />
        <Route
          path="/desk"
          element={
            <Guard roles={["staff"]}>
              <FrontDesk />
            </Guard>
          }
        />
        <Route
          path="/doctors"
          element={
            <Guard roles={["staff"]}>
              <DoctorStatus />
            </Guard>
          }
        />
        <Route
          path="/admin"
          element={
            <Guard roles={["admin"]}>
              <Dashboard />
            </Guard>
          }
        />
        <Route
          path="/analytics"
          element={
            <Guard roles={["admin"]}>
              <Analytics />
            </Guard>
          }
        />
        <Route
          path="/book"
          element={
            <Guard roles={patientRoles}>
              <Book />
            </Guard>
          }
        />
        <Route
          path="/receipt/:id"
          element={
            <Guard roles={patientRoles}>
              <Receipt />
            </Guard>
          }
        />
        <Route
          path="/notifications"
          element={
            <Guard roles={patientRoles}>
              <Notifications />
            </Guard>
          }
        />
        <Route
          path="/profile"
          element={
            <Guard roles={patientRoles}>
              <Profile />
            </Guard>
          }
        />
        <Route
          path="/calendar"
          element={
            <Guard roles={["staff"]}>
              <Calendar />
            </Guard>
          }
        />
        <Route
          path="/registration-form"
          element={
            <Guard roles={["admin"]}>
              <RegistrationForm />
            </Guard>
          }
        />
        <Route
          path="/my-queue"
          element={
            <Guard roles={["doctor"]}>
              <DoctorQueue />
            </Guard>
          }
        />
        <Route
          path="/coordination"
          element={
            <Guard roles={["staff", "admin"]}>
              <Coordination />
            </Guard>
          }
        />
        <Route
          path="/documents"
          element={
            <Guard roles={["admin"]}>
              <Documents />
            </Guard>
          }
        />
        <Route
          path="/messaging"
          element={
            <Guard roles={["admin"]}>
              <Messaging />
            </Guard>
          }
        />
        <Route
          path="/patients"
          element={
            <Guard roles={["staff", "admin"]}>
              <Patients />
            </Guard>
          }
        />
        <Route
          path="/hospital-setup"
          element={
            <Guard roles={["admin"]}>
              <HospitalSetup />
            </Guard>
          }
        />
        <Route
          path="/accounts"
          element={
            <Guard roles={["admin"]}>
              <Accounts />
            </Guard>
          }
        />
        <Route
          path="/account"
          element={
            <Guard roles={["staff", "doctor", "admin"]}>
              <Account />
            </Guard>
          }
        />
        <Route
          path="/priority-rules"
          element={
            <Guard roles={["admin"]}>
              <PriorityRules />
            </Guard>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
