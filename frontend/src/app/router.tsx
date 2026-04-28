import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "../components/layout/AppShell";
import { ChatPage } from "../pages/ChatPage";
import { UploadPage } from "../pages/UploadPage";
import { DocumentsPage } from "../pages/DocumentsPage";
import { SettingsPage } from "../pages/SettingsPage";
import { KnowledgeBasesPage } from "../pages/KnowledgeBasesPage";

export const router = createBrowserRouter(
  [
    {
      path: "/",
      element: <AppShell />,
      children: [
        { index: true, element: <Navigate to="/chat" replace /> },
        { path: "chat", element: <ChatPage /> },
        { path: "chat/:sessionId", element: <ChatPage /> },
        { path: "upload", element: <UploadPage /> },
        { path: "documents", element: <DocumentsPage /> },
        { path: "documents/:id", element: <DocumentsPage /> },
        { path: "settings", element: <SettingsPage /> },
        { path: "knowledge-bases", element: <KnowledgeBasesPage /> },
      ],
    },
  ],
  { basename: "/the-rag" }
);
