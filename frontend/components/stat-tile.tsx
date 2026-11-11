export function StatTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border p-4">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-3xl font-semibold">{value.toLocaleString("en-US")}</dd>
    </div>
  );
}
