export function PageHeader({
  title,
  description,
  actions,
  h1Ref,
}: {
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  h1Ref?: React.Ref<HTMLHeadingElement>;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
      <div className="min-w-0">
        <h1 ref={h1Ref} tabIndex={h1Ref ? -1 : undefined} className="text-2xl font-semibold tracking-tight outline-none">
          {title}
        </h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
