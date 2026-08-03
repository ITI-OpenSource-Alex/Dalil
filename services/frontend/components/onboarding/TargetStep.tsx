"use client";

import { useState } from "react";

interface TargetsData {
  destinations: string[];
  targetDegree: string;
  targetMajor: string;
  targetIntake: string;
}

interface TargetsStepProps {
  onNext: (data: TargetsData) => void;
  onBack: () => void;
  initialData?: TargetsData;
}

const AVAILABLE_COUNTRIES = [
  { id: "us", name: "United States 🇺🇸" },
  { id: "uk", name: "United Kingdom 🇬🇧" },
  { id: "ca", name: "Canada 🇨🇦" },
  { id: "de", name: "Germany 🇩🇪" },
  { id: "au", name: "Australia 🇦🇺" },
  { id: "eu", name: "Other Europe 🇪🇺" },
];

export default function TargetsStep({
  onNext,
  onBack,
  initialData,
}: TargetsStepProps) {
  const [formData, setFormData] = useState<TargetsData>({
    destinations: initialData?.destinations || [],
    targetDegree: initialData?.targetDegree || "",
    targetMajor: initialData?.targetMajor || "",
    targetIntake: initialData?.targetIntake || "",
  });

  const [errors, setErrors] = useState<Record<string, string>>({});

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};
    if (formData.destinations.length === 0)
      newErrors.destinations = "Select at least one destination country";
    if (!formData.targetDegree)
      newErrors.targetDegree = "Please select your target degree level";
    if (!formData.targetMajor.trim())
      newErrors.targetMajor = "Please enter your intended field of study";
    if (!formData.targetIntake)
      newErrors.targetIntake = "Please select your preferred start term";

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (validate()) {
      onNext(formData);
    }
  };

  const handleCountryToggle = (countryName: string) => {
    setFormData((prev) => {
      const exists = prev.destinations.includes(countryName);
      const updatedDestinations = exists
        ? prev.destinations.filter((d) => d !== countryName)
        : [...prev.destinations, countryName];
      return { ...prev, destinations: updatedDestinations };
    });
    if (errors.destinations)
      setErrors((prev) => ({ ...prev, destinations: "" }));
  };

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>,
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    if (errors[name]) setErrors((prev) => ({ ...prev, [name]: "" }));
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="space-y-1">
        <h2 className="text-xl font-bold text-black">
          Where do you want to study?
        </h2>
        <p className="text-sm text-gray-500">
          These are starting points. GOA will broaden the search as you chat.
        </p>
      </div>

      {/* Target Destinations (Multi-Select Pills) */}
      <div className="space-y-2">
        <label className="text-sm font-semibold text-black">
          Where do you want to study? (Select all that apply)
        </label>
        <div className="grid grid-cols-2 gap-2">
          {AVAILABLE_COUNTRIES.map((country) => {
            const isSelected = formData.destinations.includes(country.name);
            return (
              <button
                key={country.id}
                type="button"
                onClick={() => handleCountryToggle(country.name)}
                className={`p-3 border rounded-xl text-left transition text-sm font-medium ${
                  isSelected
                    ? "border-emerald-600 bg-emerald-50/30 text-black ring-1 ring-emerald-600"
                    : "border-gray-200 text-gray-700 hover:border-gray-300 bg-yellow-50"
                }`}
              >
                {country.name}
              </button>
            );
          })}
        </div>
        {errors.destinations && (
          <p className="text-xs font-medium text-red-500">
            {errors.destinations}
          </p>
        )}
      </div>

      {/* Target Degree Level */}
      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-semibold text-black">
          Target Degree
        </label>
        <select
          name="targetDegree"
          value={formData.targetDegree}
          onChange={handleChange}
          className={`w-full p-2.5 bg-yellow-50 border rounded-lg text-black text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 transition ${
            errors.targetDegree ? "border-red-500" : "border-gray-300"
          }`}
        >
          <option value="">Select your target degree</option>
          <option value="Bachelors">Bachelor's Degree</option>
          <option value="Masters">Master's Degree</option>
          <option value="PhD">Ph.D. / Doctorate</option>
        </select>
        {errors.targetDegree && (
          <span className="text-xs font-medium text-red-500">
            {errors.targetDegree}
          </span>
        )}
      </div>

      {/* Target Major / Field */}
      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-semibold text-black">
          Intended Major / Research Field
        </label>
        <input
          type="text"
          name="targetMajor"
          placeholder="e.g. Data Science, Mechanical Engineering"
          value={formData.targetMajor}
          onChange={handleChange}
          className={`w-full p-2.5 bg-yellow-50 border rounded-lg text-black text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 transition ${
            errors.targetMajor ? "border-red-500" : "border-gray-300"
          }`}
        />
        {errors.targetMajor && (
          <span className="text-xs font-medium text-red-500">
            {errors.targetMajor}
          </span>
        )}
      </div>

      {/* Intended Term / Intake */}
      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-semibold text-black">
          Target Intake Term
        </label>
        <select
          name="targetIntake"
          value={formData.targetIntake}
          onChange={handleChange}
          className={`w-full p-2.5 bg-yellow-50 border rounded-lg text-black text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 transition ${
            errors.targetIntake ? "border-red-500" : "border-gray-300"
          }`}
        >
          <option value="">Select an intake term</option>
          <option value="Fall 2026">Fall 2026</option>
          <option value="Spring 2027">Spring 2027</option>
          <option value="Fall 2027">Fall 2027</option>
          <option value="Later">Later</option>
        </select>
        {errors.targetIntake && (
          <span className="text-xs font-medium text-red-500">
            {errors.targetIntake}
          </span>
        )}
      </div>

      {/* Navigation Row */}
      <div className="flex gap-3 pt-2">
        <button
          type="button"
          onClick={onBack}
          className="w-1/3 border border-gray-300 text-black font-medium py-2.5 px-4 rounded-lg hover:bg-gray-50 transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-200"
        >
          Back
        </button>
        <button
          type="submit"
          className="w-2/3 bg-emerald-600 hover:bg-emerald-700 text-white font-medium py-2.5 px-4 rounded-lg shadow-sm transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-emerald-500"
        >
          Continue
        </button>
      </div>
    </form>
  );
}
