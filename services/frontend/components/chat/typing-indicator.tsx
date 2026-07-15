"use client";

import { motion } from "framer-motion";

export default function TypingIndicator() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 8 }}
      transition={{ duration: 0.2 }}
      className="flex gap-4 justify-start"
    >
      {/* Assistant Avatar */}
      <div className="w-8 h-8 rounded-full bg-[#0E3D23] flex items-center justify-center text-white text-xs font-semibold shrink-0">
        G
      </div>

      {/* Bubble */}
      <div className="bg-white border border-[#EBEFEA] rounded-2xl rounded-tl-none px-4 py-3 shadow-sm">
        <div className="flex items-center gap-1.5">
          <motion.span
            className="w-2 h-2 rounded-full bg-emerald-500"
            animate={{ y: [0, -4, 0] }}
            transition={{
              repeat: Infinity,
              duration: 0.7,
              delay: 0,
            }}
          />
          <motion.span
            className="w-2 h-2 rounded-full bg-emerald-500"
            animate={{ y: [0, -4, 0] }}
            transition={{
              repeat: Infinity,
              duration: 0.7,
              delay: 0.15,
            }}
          />
          <motion.span
            className="w-2 h-2 rounded-full bg-emerald-500"
            animate={{ y: [0, -4, 0] }}
            transition={{
              repeat: Infinity,
              duration: 0.7,
              delay: 0.3,
            }}
          />
        </div>
      </div>
    </motion.div>
  );
}
