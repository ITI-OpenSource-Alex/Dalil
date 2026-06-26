import HeroChat from "./HeroChat";
import HeroContent from "./HeroContent";

export default function Hero() {
  return (
    <section className="overflow-hidden bg-gradient-to-br from-emerald-50 via-white to-orange-50 py-24">
      <div className="mx-auto grid max-w-7xl items-center gap-20 px-6 lg:grid-cols-2">
        <HeroContent />
        <HeroChat />
      </div>
    </section>
  );
}
