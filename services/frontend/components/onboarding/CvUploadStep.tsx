"use client";

import { useState, useRef } from "react";

interface CvUploadStepProps {
  onComplete: (cvData: { fileName: string; skipped: boolean } | null) => void;
  onBack: () => void;
}

export default function CvUploadStep({
  onComplete,
  onBack,
}: CvUploadStepProps) {
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [status, setStatus] = useState<
    "idle" | "uploading" | "processing" | "done"
  >("idle");
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Simulate file upload progress, then simulate Lambda background extraction processing
  const simulateUploadAndProcessing = (selectedFile: File) => {
    setFile(selectedFile);
    setStatus("uploading");
    setUploadProgress(0);

    // 1. Simulate Upload Progress
    const uploadInterval = setInterval(() => {
      setUploadProgress((prev) => {
        if (prev >= 100) {
          clearInterval(uploadInterval);

          // 2. Transition to Lambda "Processing..." State
          setStatus("processing");
          setTimeout(() => {
            setStatus("done");
            // Finish up and transition automatically to chat
            onComplete({ fileName: selectedFile.name, skipped: false });
          }, 2500); // Lambda parsing delay simulation

          return 100;
        }
        return prev + 10;
      });
    }, 150);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    if (status === "idle") setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (status !== "idle") return;

    const droppedFile = e.dataTransfer.files?.[0];
    if (droppedFile && droppedFile.type === "application/pdf") {
      simulateUploadAndProcessing(droppedFile);
    } else {
      alert("Please upload a valid PDF document.");
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      simulateUploadAndProcessing(selectedFile);
    }
  };

  const handleSkip = () => {
    onComplete({ fileName: "", skipped: true });
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-start">
        <div className="space-y-1">
          <h2 className="text-xl font-bold text-black">
            Upload your latest CV
          </h2>
          <p className="text-sm text-gray-500">
            Optional, but unlocks personalized program ranking and CV review.
          </p>
        </div>
        {status === "idle" && (
          <button
            type="button"
            onClick={handleSkip}
            className="text-xs font-semibold text-gray-400 hover:text-black uppercase tracking-wider bg-gray-50 hover:bg-yellow-50 transition px-2.5 py-1.5 rounded-md"
          >
            Skip step
          </button>
        )}
      </div>

      {/* DRAG AND DROP ZONE */}
      {status === "idle" && (
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition flex flex-col items-center justify-center min-h-55 ${
            isDragging
              ? "border-emerald-600 bg-emerald-50/20"
              : "border-gray-200 hover:border-emerald-500 hover:bg-gray-50/50 bg-white"
          }`}
        >
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            accept=".pdf"
            className="hidden"
          />
          <div className="w-12 h-12 rounded-full bg-emerald-50 flex items-center justify-center text-emerald-600 text-xl mb-3">
            📥
          </div>
          <p className="text-sm font-semibold text-black mb-1">
            Drag & drop your resume file here
          </p>
          <p className="text-xs text-gray-400 mb-4">
            Only PDF formats are supported
          </p>
          <button
            type="button"
            className="px-4 py-2 border border-gray-200 hover:border-gray-300 text-black text-xs font-medium rounded-lg bg-white shadow-sm transition"
          >
            Browse files
          </button>
        </div>
      )}

      {/* UPLOADING STATE VIEW */}
      {status === "uploading" && (
        <div className="border border-gray-100 bg-gray-50/40 rounded-xl p-6 space-y-4 animate-fadeIn">
          <div className="flex items-center justify-between text-sm">
            <span className="font-semibold text-black truncate max-w-[70%]">
              📄 {file?.name}
            </span>
            <span className="text-xs font-bold text-emerald-600">
              {uploadProgress}%
            </span>
          </div>
          <div className="w-full h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-emerald-500 transition-all duration-150 ease-out"
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
          <p className="text-xs text-center text-gray-400 font-medium">
            Uploading document to secure storage...
          </p>
        </div>
      )}

      {/* EXTRACTING / PROCESSING STATE VIEW (LAMBDA CALLOUT) */}
      {status === "processing" && (
        <div className="border border-emerald-100 bg-emerald-50/20 rounded-xl p-8 text-center space-y-4 animate-fadeIn">
          <div className="inline-flex relative items-center justify-center">
            {/* Spinning Indicator Ring */}
            <div className="w-10 h-10 border-2 border-emerald-200 border-t-emerald-600 rounded-full animate-spin" />
            <span className="absolute text-sm">✨</span>
          </div>
          <div className="space-y-1">
            <h4 className="text-sm font-bold text-black">
              Processing Document...
            </h4>
            <p className="text-xs text-gray-500 max-w-sm mx-auto">
              Our AI engine is parsing your credentials and structuring your
              career milestones.
            </p>
          </div>
        </div>
      )}

      {/* DONE STATE VIEW */}
      {status === "done" && (
        <div className="border border-gray-100 bg-white rounded-xl p-8 text-center space-y-2 animate-fadeIn">
          <div className="w-10 h-10 bg-emerald-500 text-white rounded-full flex items-center justify-center mx-auto text-lg shadow-sm">
            ✓
          </div>
          <h4 className="text-sm font-bold text-black pt-1">
            Success! Profile Synchronized
          </h4>
        </div>
      )}

      {/* NAVIGATION FOOTER */}
      {status === "idle" && (
        <div className="flex gap-3 pt-2">
          <button
            type="button"
            onClick={onBack}
            className="w-full border border-gray-300 text-black font-medium py-2.5 px-4 rounded-lg hover:bg-gray-50 transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-200"
          >
            Back to Targets
          </button>
        </div>
      )}
    </div>
  );
}
