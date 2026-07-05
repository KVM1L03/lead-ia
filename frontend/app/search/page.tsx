import { LeadSearchForm } from "@/components/LeadSearchForm";

export default function SearchPage() {
  const demoMode = process.env.EXECUTION_MODE === "sync";
  return <LeadSearchForm demoMode={demoMode} />;
}
