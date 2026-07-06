const stats = [
  {
    value: "120+",
    label: "Universities",
  },
  {
    value: "30+",
    label: "Countries",
  },
  {
    value: "95%",
    label: "Match Accuracy",
  },
];

export default function HeroStats() {
  return (
    <div className="mt-12 flex gap-10">
      {stats.map((item) => (
        <div key={item.label}>
          <h3 className="text-3xl font-bold text-slate-900">{item.value}</h3>
          <p className="mt-1 text-sm text-slate-500">{item.label}</p>
        </div>
      ))}
    </div>
  );
}
