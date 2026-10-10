import { ItemsPanel } from "@/components/items-panel";

export default function Home() {
  return (
    <main className="mx-auto flex max-w-[1280px] flex-col gap-12 px-6 py-16">
      <header className="flex flex-col gap-3">
        <span className="text-caption uppercase text-mid-gray">Next.js · FastAPI · PostgreSQL</span>
        <h1 className="text-display font-semibold">Monorepo starter</h1>
        <p className="max-w-xl text-body-lg text-mid-gray">
          The frontend talks to the backend through <code className="font-mono">/api</code>; the
          backend persists items in PostgreSQL through its service and repository layers.
        </p>
      </header>
      <ItemsPanel />
    </main>
  );
}
