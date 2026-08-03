import Link from "next/link";

const linkColumns = [
  {
    heading: "Product",
    links: [
      { label: "Features", href: "#features" },
      { label: "How it works", href: "#how-it-works" },
      { label: "Pricing", href: "#pricing" },
    ],
  },
  {
    heading: "Company",
    links: [
      { label: "About", href: "#" },
      { label: "Contact", href: "#" },
    ],
  },
  {
    heading: "Legal",
    links: [
      { label: "Privacy Policy", href: "#" },
      { label: "Terms of Service", href: "#" },
    ],
  },
];

export default function Footer() {
  return (
    <footer className="border-t border-slate-200 bg-white py-16">
      <div className="mx-auto max-w-7xl px-6">
        <div className="grid grid-cols-2 gap-10 md:grid-cols-4">
          <div className="col-span-2 md:col-span-1">
            <Link
              href="/"
              className="text-3xl font-bold tracking-tight text-slate-900"
            >
              GOA
            </Link>
            <p className="mt-3 max-w-xs text-sm leading-6 text-slate-500">
              The AI study abroad platform — matching, checklists and IELTS
              prep in one assistant.
            </p>
          </div>

          {linkColumns.map((column) => (
            <div key={column.heading}>
              {/* Not a heading element: this footer sits after Pricing's
                  <h2>, and these labels aren't a subsection of it -- an
                  <h3> here would skip a level in the page's heading
                  hierarchy for no semantic benefit. */}
              <p className="text-sm font-semibold text-slate-900">
                {column.heading}
              </p>
              <ul className="mt-4 space-y-3">
                {column.links.map((link) => (
                  <li key={link.label}>
                    <Link
                      href={link.href}
                      className="text-sm text-slate-500 transition hover:text-slate-900"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-12 border-t border-slate-200 pt-8">
          <p className="text-sm text-slate-500">
            © {new Date().getFullYear()} GOA. All rights reserved.
          </p>
        </div>
      </div>
    </footer>
  );
}
