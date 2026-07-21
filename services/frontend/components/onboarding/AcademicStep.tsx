"use client";

import { useState } from "react";

interface AcademicData {
  degree: string;
  major: string;
  university: string;
  gradYear: string;
  gpa: string;
  ECTScred: string;
}

interface AcademicStepProps {
  onNext: (data: AcademicData) => void;
  initialData?: AcademicData;
}

export default function AcademicStep({
  onNext,
  initialData,
}: AcademicStepProps) {
  const [formData, setFormData] = useState<AcademicData>({
    degree: initialData?.degree || "",
    major: initialData?.major || "",
    university: initialData?.university || "",
    gradYear: initialData?.gradYear || "",
    gpa: initialData?.gpa || "",
    ECTScred: initialData?.ECTScred || "",
  });

  const [errors, setErrors] = useState<Partial<AcademicData>>({});

  const validate = (): boolean => {
    const newErrors: Partial<AcademicData> = {};
    if (!formData.degree) newErrors.degree = "Degree level is required";
    if (!formData.major.trim()) newErrors.major = "Major is required";
    if (!formData.university.trim())
      newErrors.university = "University name is required";
    if (!formData.gradYear) {
      newErrors.gradYear = "Graduation year is required";
    } else {
      const year = parseInt(formData.gradYear, 10);
      if (isNaN(year) || year < 1950 || year > 2035) {
        newErrors.gradYear =
          "Please enter a valid graduation year (1950 - 2035)";
      }
    }

    if (!formData.gpa.trim()) newErrors.gpa = "GPA is required";

    if (!formData.ECTScred) {
      newErrors.ECTScred = "ECTS credir score is required";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (validate()) {
      onNext(formData);
    }
  };

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>,
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    // Clear error dynamically as the user types/selects
    if (errors[name as keyof AcademicData]) {
      setErrors((prev) => ({ ...prev, [name]: undefined }));
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div className="space-y-1">
        <h2 className="text-xl font-bold text-black">
          Tell us about your education
        </h2>
        <p className="text-sm text-gray-500">
          We use this to match you with programs that fit your background.
        </p>
      </div>

      {/* Degree Select */}
      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-semibold text-black">Degree Level</label>
        <select
          name="degree"
          value={formData.degree}
          onChange={handleChange}
          className={`w-full p-2.5 bg-yellow-50 border rounded-lg text-black focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 transition ${
            errors.degree ? "border-red-500" : "border-gray-300"
          }`}
        >
          <option value="">Select your degree</option>
          <option value="Bachelors">Bachelor's Degree</option>
          <option value="Masters">Master's Degree</option>
          <option value="PhD">Ph.D. / Doctorate</option>
          <option value="Diploma">Diploma / Other</option>
        </select>
        {errors.degree && (
          <span className="text-xs font-medium text-red-500">
            {errors.degree}
          </span>
        )}
      </div>

      {/* major of Study */}
      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-semibold text-black">Major</label>
        <input
          type="text"
          name="major"
          placeholder="e.g. Computer Science, Business Administration"
          value={formData.major}
          onChange={handleChange}
          className={`w-full p-2.5 bg-yellow-50 border rounded-lg text-black focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 transition ${
            errors.major ? "border-red-500" : "border-gray-300"
          }`}
        />
        {errors.major && (
          <span className="text-xs font-medium text-red-500">
            {errors.major}
          </span>
        )}
      </div>

      {/* university Name */}
      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-semibold text-black">
          Institution / University
        </label>
        <input
          type="text"
          name="university"
          placeholder="e.g. Stanford University"
          value={formData.university}
          onChange={handleChange}
          className={`w-full p-2.5 bg-yellow-50 border rounded-lg text-black focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 transition ${
            errors.university ? "border-red-500" : "border-gray-300"
          }`}
        />
        {errors.university && (
          <span className="text-xs font-medium text-red-500">
            {errors.university}
          </span>
        )}
      </div>

      {/* Graduation Year */}
      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-semibold text-black">
          Graduation Year (or Expected)
        </label>
        <input
          type="number"
          name="gradYear"
          placeholder="e.g. 2024"
          value={formData.gradYear}
          onChange={handleChange}
          className={`w-full p-2.5 bg-yellow-50 border rounded-lg text-black focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 transition [appearance:textmajor] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none ${
            errors.gradYear ? "border-red-500" : "border-gray-300"
          }`}
        />
        {errors.gradYear && (
          <span className="text-xs font-medium text-red-500">
            {errors.gradYear}
          </span>
        )}
      </div>

      {/* GPA (String) & ECTS Credits (Number) Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* GPA Input */}
        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-semibold text-black">
            GPA / Grade
          </label>
          <input
            type="text"
            name="gpa"
            placeholder="e.g. 3.8/4.0 or Excellent"
            value={formData.gpa}
            onChange={handleChange}
            className={`w-full p-2.5 bg-yellow-50 border rounded-lg text-black focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 transition ${
              errors.gpa ? "border-red-500" : "border-gray-300"
            }`}
          />
          {errors.gpa && (
            <span className="text-xs font-medium text-red-500">
              {errors.gpa}
            </span>
          )}
        </div>

        {/* ECTS Credits Input */}
        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-semibold text-black">
            ECTS Credits
          </label>
          <input
            type="text"
            name="ECTScred"
            placeholder="e.g. 180"
            value={formData.ECTScred}
            onChange={handleChange}
            className={`w-full p-2.5 bg-yellow-50 border rounded-lg text-black focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 transition [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none ${
              errors.ECTScred ? "border-red-500" : "border-gray-300"
            }`}
          />
          {errors.ECTScred && (
            <span className="text-xs font-medium text-red-500">
              {errors.ECTScred}
            </span>
          )}
        </div>
      </div>

      {/* Navigation */}
      <div className="pt-2">
        <button
          type="submit"
          className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-medium py-2.5 px-4 rounded-lg shadow-sm transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-emerald-500"
        >
          Continue
        </button>
      </div>
    </form>
  );
}
