import { Explorer } from "@/components/explorer/explorer";

export const dynamic = "force-dynamic";

export default async function RunPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <Explorer runId={id} />;
}
