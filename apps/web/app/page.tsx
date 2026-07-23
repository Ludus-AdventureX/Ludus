import { DecisionShell } from "@/components/shell/DecisionShell";
import { SessionBootstrap } from "@/components/shell/SessionBootstrap";

export default function Home() {
  return (
    <SessionBootstrap>
      <DecisionShell />
    </SessionBootstrap>
  );
}