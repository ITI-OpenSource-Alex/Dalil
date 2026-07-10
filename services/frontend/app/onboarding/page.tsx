"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import AcademicStep from "@/components/onboarding/AcademicStep";
import LanguageStep from "@/components/onboarding/LanguageStep";
import TargetsStep from "@/components/onboarding/TargetStep";
import CvUploadStep from "@/components/onboarding/CvUploadStep";

export default function OnboardingWizardPage() {
  const router = useRouter();
  const [currentStep, setCurrentStep] = useState(1);
  const [formData, setFormData] = useState({
    academic: {},
    language: {},
    targets: {},
    cv: null,
  });

  const totalSteps = 4;

  const handleNextStep = (stepData: any, key: string) => {
    setFormData((prev) => ({ ...prev, [key]: stepData }));
    setCurrentStep((prev) => Math.min(prev + 1, totalSteps));
  };

  const handleBackStep = () => {
    setCurrentStep((prev) => Math.max(prev - 1, 1));
  };

  const handleFinish = () => {
    // Final save logic can go here
    router.push("/chat");
  };

  const stepNames = ["Academic", "Languages", "Targets", "CV Upload"];

  return (
    <div className="min-h-screen bg-linear-to-br from-emerald-50 via-white to-yellow-50 flex flex-col justify-center items-center p-6">
      <div className="w-full max-w-xl bg-white border border-gray-100 shadow-xl rounded-2xl p-8">
        {/* Progress Bar Header */}
        <div className="mb-8">
          <div className="flex justify-between items-center mb-4">
            <span className="text-xs font-semibold uppercase tracking-wider text-emerald-600">
              Step {currentStep} of {totalSteps}
            </span>
            <span className="text-sm font-medium text-black">
              {stepNames[currentStep - 1]}
            </span>
          </div>

          {/* Progress bar track */}
          <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-emerald-500 transition-all duration-300 ease-in-out"
              style={{ width: `${(currentStep / totalSteps) * 100}%` }}
            />
          </div>
        </div>

        {/* Dynamic Step Content */}
        <div className="mt-4">
          {currentStep === 1 && (
            <AcademicStep
              initialData={formData.academic as any}
              onNext={(data) => handleNextStep(data, "academic")}
            />
          )}
          {currentStep === 2 && (
            <LanguageStep
              initialData={formData.language as any}
              onNext={(data) => handleNextStep(data, "language")}
              onBack={handleBackStep}
            />
          )}
          {currentStep === 3 && (
            <TargetsStep
              initialData={formData.targets as any}
              onNext={(data) => handleNextStep(data, "targets")}
              onBack={handleBackStep}
            />
          )}
          {currentStep === 4 && (
            <CvUploadStep onComplete={handleFinish} onBack={handleBackStep} />
          )}
        </div>
      </div>
    </div>
  );
}
