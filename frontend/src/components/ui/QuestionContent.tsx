"use client";

import React from "react";
import { MathRenderer } from "./MathRenderer";
import { prepareQuestionVisuals, type QuestionVisual } from "../../lib/api/question-visuals";

interface Props {
  content: string;
  visuals?: readonly QuestionVisual[];
  role?: QuestionVisual["role"];
  gallery?: boolean;
  relatedContent?: readonly string[];
  inline?: boolean;
  className?: string;
}

export function QuestionContent({ content, visuals = [], role = "question", gallery = true,
  relatedContent = [], inline, className }: Props) {
  return <MathRenderer content={prepareQuestionVisuals(content, visuals, role, gallery, relatedContent)}
    inline={inline} className={className} />;
}
