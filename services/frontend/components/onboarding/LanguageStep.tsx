"use client";

import { useState } from "react";

interface LanguageData {
  hasTakenIelts: "yes" | "no" | "";
  // Yes branch fields
  listeningScore: string;
  readingScore: string;
  writingScore: string;
  speakingScore: string;
  overallScore: string;
  // No branch fields
  planningToTake: "yes" | "no" | "";
  targetOverallScore: string;
  targetExamDate: string;
}

interface LanguageStepProps {
  onNext: (data: LanguageData) => void;
  onBack: () => void;
  initialData?: LanguageData;
}

export default function LanguageStep({
  onNext,
  onBack,
  initialData,
}: LanguageStepProps) {
  const [formData, setFormData] = useState<LanguageData>({
    hasTakenIelts: initialData?.hasTakenIelts || "",
    listeningScore: initialData?.listeningScore || "",
    readingScore: initialData?.readingScore || "",
    writingScore: initialData?.writingScore || "",
    speakingScore: initialData?.speakingScore || "",
    overallScore: initialData?.overallScore || "",
    planningToTake: initialData?.planningToTake || "",
    targetOverallScore: initialData?.targetOverallScore || "",
    targetExamDate: initialData?.targetExamDate || "",
  });

  const [errors, setErrors] = useState<Record<string, string>>({});

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!formData.hasTakenIelts) {
      newErrors.hasTakenIelts = "Please select whether you have taken IELTS.";
    } else if (formData.hasTakenIelts === "yes") {
      // Validate all sub-scores and overall score
      const scoreFields = [
        "listeningScore",
        "readingScore",
        "writingScore",
        "speakingScore",
        "overallScore",
      ];
      scoreFields.forEach((field) => {
        const val = formData[field as keyof LanguageData];
        if (!val) {
          newErrors[field] = "Required";
        } else {
          const num = parseFloat(val);
          if (isNaN(num) || num < 0 || num > 9 || num % 0.5 !== 0) {
            newErrors[field] = "Must be 0-9 (0.5 steps)";
          }
        }
      });
    } else if (formData.hasTakenIelts === "no") {
      if (!formData.planningToTake) {
        newErrors.planningToTake =
          "Please let us know if you are planning to take IELTS.";
      } else if (formData.planningToTake === "yes") {
        if (!formData.targetOverallScore) {
          newErrors.targetOverallScore = "Target score is required";
        } else {
          const num = parseFloat(formData.targetOverallScore);
          if (isNaN(num) || num < 0 || num > 9) {
            newErrors.targetOverallScore = "Must be between 0 and 9";
          }
        }
        if (!formData.targetExamDate) {
          newErrors.targetExamDate = "Target date is required";
        }
      }
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

  const handleRadioChange = (name: keyof LanguageData, value: string) => {
    setFormData((prev) => {
      const updated = { ...prev, [name]: value };
      // Reset dependent fields when core choice changes
      if (name === "hasTakenIelts") {
        updated.listeningScore = "";
        updated.readingScore = "";
        updated.writingScore = "";
        updated.speakingScore = "";
        updated.overallScore = "";
        updated.planningToTake = "";
        updated.targetOverallScore = "";
        updated.targetExamDate = "";
      } else if (name === "planningToTake") {
        updated.targetOverallScore = "";
        updated.targetExamDate = "";
      }
      return updated;
    });
    setErrors({});
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    if (errors[name]) {
      setErrors((prev) => ({ ...prev, [name]: "" }));
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="space-y-1">
        <h2 className="text-xl font-bold text-black">How's your English?</h2>
        <p className="text-sm text-gray-500">
          We'll never reject you for a low score — we'll explain the gap and
          plan around it.
        </p>
      </div>

      {/* Question 1: Have you taken IELTS? */}
      <div className="space-y-2">
        <label className="text-sm font-semibold text-black">
          Have you taken IELTS before?
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <button
            type="button"
            onClick={() => handleRadioChange("hasTakenIelts", "yes")}
            className={`p-3 border rounded-xl text-left transition font-medium text-sm flex items-center justify-between ${
              formData.hasTakenIelts === "yes"
                ? "border-emerald-600 bg-emerald-50/30 text-black ring-1 ring-emerald-600"
                : "border-gray-200 text-gray-700 hover:border-gray-300 bg-yellow-50"
            }`}
          >
            <span>Yes, I have a score</span>
            <div
              className={`w-4 h-4 rounded-full border flex items-center justify-center ${formData.hasTakenIelts === "yes" ? "border-emerald-600" : "border-gray-300"}`}
            >
              {formData.hasTakenIelts === "yes" && (
                <div className="w-2 h-2 rounded-full bg-emerald-600" />
              )}
            </div>
          </button>

          <button
            type="button"
            onClick={() => handleRadioChange("hasTakenIelts", "no")}
            className={`p-3 border rounded-xl text-left transition font-medium text-sm flex items-center justify-between ${
              formData.hasTakenIelts === "no"
                ? "border-emerald-600 bg-emerald-50/30 text-black ring-1 ring-emerald-600"
                : "border-gray-200 text-gray-700 hover:border-gray-300 bg-yellow-50"
            }`}
          >
            <span>Not yet</span>
            <div
              className={`w-4 h-4 rounded-full border flex items-center justify-center ${formData.hasTakenIelts === "no" ? "border-emerald-600" : "border-gray-300"}`}
            >
              {formData.hasTakenIelts === "no" && (
                <div className="w-2 h-2 rounded-full bg-emerald-600" />
              )}
            </div>
          </button>
        </div>
        {errors.hasTakenIelts && (
          <p className="text-xs font-medium text-red-500">
            {errors.hasTakenIelts}
          </p>
        )}
      </div>

      {/* BRANCH 1: YES, HAVE SCORE */}
      {formData.hasTakenIelts === "yes" && (
        <div className="p-4 bg-orange-50 border border-gray-100 rounded-xl space-y-4 animate-fadeIn">
          <h3 className="text-sm font-bold text-black uppercase tracking-wider">
            Enter your scores
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { id: "listeningScore", label: "Listening" },
              { id: "readingScore", label: "Reading" },
              { id: "writingScore", label: "Writing" },
              { id: "speakingScore", label: "Speaking" },
            ].map((field) => (
              <div key={field.id} className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-gray-700">
                  {field.label}
                </label>
                <input
                  type="number"
                  step="0.5"
                  name={field.id}
                  placeholder="0.0"
                  value={formData[field.id as keyof LanguageData]}
                  onChange={handleInputChange}
                  className={`w-full p-2 text-center bg-white border rounded-lg text-black text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none ${
                    errors[field.id] ? "border-red-500" : "border-gray-200"
                  }`}
                />
                {errors[field.id] && (
                  <span className="text-[10px] font-medium text-red-500 text-center">
                    {errors[field.id]}
                  </span>
                )}
              </div>
            ))}
          </div>

          <div className="flex flex-col gap-1.5 max-w-40 mx-auto pt-2">
            <label className="text-xs font-bold text-center text-black uppercase tracking-wide">
              Overall Band Score
            </label>
            <input
              type="number"
              step="0.5"
              name="overallScore"
              placeholder="0.0"
              value={formData.overallScore}
              onChange={handleInputChange}
              className={`w-full p-2.5 text-center font-bold bg-white border rounded-lg text-black text-base focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none ${
                errors.overallScore
                  ? "border-red-500 font-normal text-xs"
                  : "border-gray-300 border-emerald-600/30"
              }`}
            />
            {errors.overallScore && (
              <span className="text-[10px] font-medium text-red-500 text-center">
                {errors.overallScore}
              </span>
            )}
          </div>
        </div>
      )}

      {/* BRANCH 2: NOT YET */}
      {formData.hasTakenIelts === "no" && (
        <div className="space-y-4 animate-fadeIn">
          <div className="space-y-2">
            <label className="text-sm font-semibold text-black">
              Planning to take it?
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => handleRadioChange("planningToTake", "yes")}
                className={`p-3 border rounded-xl text-left transition font-medium text-sm flex items-center justify-between ${
                  formData.planningToTake === "yes"
                    ? "border-emerald-600 bg-emerald-50/30 text-black ring-1 ring-emerald-600"
                    : "border-gray-200 text-gray-700 hover:border-gray-300 bg-yellow-50"
                }`}
              >
                <span>Yes, Planning</span>
                <div
                  className={`w-4 h-4 rounded-full border flex items-center justify-center ${formData.planningToTake === "yes" ? "border-emerald-600" : "border-gray-300"}`}
                >
                  {formData.planningToTake === "yes" && (
                    <div className="w-2 h-2 rounded-full bg-emerald-600" />
                  )}
                </div>
              </button>

              <button
                type="button"
                onClick={() => handleRadioChange("planningToTake", "no")}
                className={`p-3 border rounded-xl text-left transition font-medium text-sm flex items-center justify-between ${
                  formData.planningToTake === "no"
                    ? "border-emerald-600 bg-emerald-50/30 text-black ring-1 ring-emerald-600"
                    : "border-gray-200 text-gray-700 hover:border-gray-300 bg-yellow-50"
                }`}
              >
                <span>Not sure yet</span>
                <div
                  className={`w-4 h-4 rounded-full border flex items-center justify-center ${formData.planningToTake === "no" ? "border-emerald-600" : "border-gray-300"}`}
                >
                  {formData.planningToTake === "no" && (
                    <div className="w-2 h-2 rounded-full bg-emerald-600" />
                  )}
                </div>
              </button>
            </div>
            {errors.planningToTake && (
              <p className="text-xs font-medium text-red-500">
                {errors.planningToTake}
              </p>
            )}
          </div>

          {/* SUB-BRANCH: YES, PLANNING */}
          {formData.planningToTake === "yes" && (
            <div className="p-4 bg-yellow-50 border border-gray-100 rounded-xl space-y-4 animate-fadeIn">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-black">
                    Targeted Overall Score
                  </label>
                  <input
                    type="number"
                    step="0.5"
                    name="targetOverallScore"
                    placeholder="e.g. 7.5"
                    value={formData.targetOverallScore}
                    onChange={handleInputChange}
                    className={`w-full p-2.5 bg-white border rounded-lg text-black text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none ${
                      errors.targetOverallScore
                        ? "border-red-500"
                        : "border-gray-200"
                    }`}
                  />
                  {errors.targetOverallScore && (
                    <span className="text-[10px] font-medium text-red-500">
                      {errors.targetOverallScore}
                    </span>
                  )}
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-black">
                    Target Exam Date
                  </label>
                  <input
                    type="date"
                    name="targetExamDate"
                    value={formData.targetExamDate}
                    onChange={handleInputChange}
                    className={`w-full p-2.5 bg-white border rounded-lg text-black text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 ${
                      errors.targetExamDate
                        ? "border-red-500"
                        : "border-gray-200"
                    }`}
                  />
                  {errors.targetExamDate && (
                    <span className="text-[10px] font-medium text-red-500">
                      {errors.targetExamDate}
                    </span>
                  )}
                </div>
              </div>

              {/* Dynamic checklist alert text */}
              <div className="p-3 bg-emerald-50 border border-emerald-100 rounded-lg text-xs font-medium text-emerald-800">
                ✨ We'll add IELTS preparation tasks to your checklist
                automatically.
              </div>
            </div>
          )}
        </div>
      )}

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
