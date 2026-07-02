import type { Metadata } from "next";
import { Source_Serif_4, Inter, IBM_Plex_Mono } from "next/font/google";
import { Toast } from "@base-ui/react/toast";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { Topbar } from "@/components/Topbar";
import { ToastRegion } from "@/components/ToastRegion";

const sourceSerif = Source_Serif_4({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-source-serif",
  display: "swap",
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-ibm-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "LeadForge",
  description: "AI-powered B2B lead generation pipeline",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${sourceSerif.variable} ${inter.variable} ${ibmPlexMono.variable} h-full`}
    >
      <body className="h-full bg-background text-foreground font-sans antialiased">
        <Toast.Provider>
          <Sidebar />
          <div className="ml-[220px] flex flex-col min-h-screen">
            <Topbar />
            <main className="flex-1">{children}</main>
          </div>
          <ToastRegion />
        </Toast.Provider>
      </body>
    </html>
  );
}
