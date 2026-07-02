export default async function RunPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <section className="px-8 py-10">
      <p className="font-mono font-medium text-[11px] uppercase tracking-[.18em] text-muted-fg mb-4">
        Run
      </p>
      <h1 className="font-serif text-[28px] leading-[1.35] tracking-[-0.015em] text-fg">
        {id}
      </h1>
    </section>
  );
}
