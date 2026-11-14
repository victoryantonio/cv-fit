import { errorMessage } from "@/api/client";
import {
  commandFromError,
  useConnectGmail,
  useDisconnectGmail,
} from "@/api/gmail";
import { describeStatus, useHealth } from "@/api/health";
import { Button } from "@/components/Button";

export function GmailTab() {
  const health = useHealth();
  const connect = useConnectGmail();
  const disconnect = useDisconnectGmail();

  const state = health.data?.gmail ?? "unknown";
  const connected = state === "connected";
  const command = commandFromError(connect.error);

  return (
    <div className="space-y-8">
      <section aria-labelledby="state" className="space-y-2">
        <h2 id="state" className="text-section">
          Connection
        </h2>
        <p className="text-dense">
          Status:{" "}
          <strong>
            {health.isPending ? "Checking..." : describeStatus(state)}
          </strong>
        </p>
        <p className="text-dense text-muted">
          Consent is granted to a separate helper process and the token is
          stored in the OS keychain. This app never holds an OAuth code and
          never talks to Google itself.
        </p>
      </section>

      <section aria-labelledby="scope" className="space-y-2">
        <h2 id="scope" className="text-section">
          Scope
        </h2>
        <p className="text-dense">
          <code className="rounded-sm border border-line px-1.5 py-0.5 text-dense">
            gmail.readonly
          </code>{" "}
          — job-alert emails are read, then turned into rows. Nothing is sent,
          labelled, archived or deleted.
        </p>
        <p className="text-dense text-muted">
          The helper exposes exactly two tools and no others, so a wider read is
          not possible from here. Unreadable alerts are skipped, never guessed
          at.
        </p>
      </section>

      <section aria-labelledby="actions" className="space-y-3">
        <h2 id="actions" className="text-section">
          Actions
        </h2>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="ghost"
            busy={connect.isPending}
            onClick={() => connect.mutate()}
          >
            {connected ? "Re-check" : "Check connection"}
          </Button>
          <Button
            variant="ghost"
            busy={disconnect.isPending}
            disabled={!connected}
            onClick={() => disconnect.mutate()}
          >
            Disconnect
          </Button>
        </div>
        {connect.data && connect.data.status === "connected" ? (
          <p role="status" className="text-dense">
            Gmail is connected. Sync from the job inbox.
          </p>
        ) : null}
        {command ? (
          <div className="rounded-sm border border-line px-3 py-2">
            <p className="text-dense">
              Run this in a terminal, then check again:
            </p>
            <code className="mt-1 block text-dense">{command}</code>
          </div>
        ) : null}
        {connect.isError && !command ? (
          <p role="alert" className="text-dense text-danger">
            {errorMessage(connect.error)}
          </p>
        ) : null}
        {disconnect.isError ? (
          <p role="alert" className="text-dense text-danger">
            {errorMessage(disconnect.error)}
          </p>
        ) : null}
        {disconnect.data ? (
          <p role="status" className="text-dense">
            The stored token was removed. Alerts will not sync until you
            authenticate again.
          </p>
        ) : null}
      </section>
    </div>
  );
}
