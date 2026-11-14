import { createBrowserRouter } from "react-router-dom";

import { AppShell } from "./AppShell";
import { AnalysisTask } from "@/routes/AnalysisTask";
import { Cvs } from "@/routes/Cvs";
import { Home } from "@/routes/Home";
import { JobDetail } from "@/routes/JobDetail";
import { Jobs } from "@/routes/Jobs";
import { NotFound } from "@/routes/NotFound";
import { Packet } from "@/routes/Packet";
import { ParserView } from "@/routes/ParserView";
import { Settings } from "@/routes/Settings";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Home /> },
      { path: "jobs", element: <Jobs /> },
      { path: "jobs/:jobId", element: <JobDetail /> },
      { path: "cvs", element: <Cvs /> },
      { path: "cv-versions/:versionId", element: <ParserView /> },
      { path: "tasks/:taskId", element: <AnalysisTask /> },
      { path: "analyses/:analysisId", element: <Packet /> },
      { path: "settings", element: <Settings /> },
      { path: "*", element: <NotFound /> },
    ],
  },
]);
