import test from "node:test";
import assert from "node:assert/strict";
import {compareMathRecognizers,normalizedMathTokens,unwrapMathOutput} from "../src/features/math-workspace/utils/math-recognizer-comparison.js";
test("raw strict result and declared formatting normalization stay distinct",()=>{
 const raw="```latex\n\\[\\frac12\\]\n```";
 assert.equal(unwrapMathOutput(raw),"\\frac12");
 const m=compareMathRecognizers(raw,"\\frac{1}{2}");assert.equal(m.strictExact,false);assert.equal(m.normalizedExact,true);
 assert.deepEqual(normalizedMathTokens("\\frac12"),normalizedMathTokens("\\frac{1}{2}"));
});
test("normalization never repairs a mathematically wrong answer or changes relation symbols",()=>{
 assert.equal(compareMathRecognizers("x+1=3 \\Rightarrow x=2","x+1=3 \\Rightarrow x=5").normalizedExact,false);
 assert.equal(compareMathRecognizers("x \\Rightarrow y","x \\Leftrightarrow y").normalizedExact,false);
});
test("token alignment separates missing, extra and substitutions",()=>{
 const missing=compareMathRecognizers("x=","x=5");assert.equal(missing.missingTokens,1);assert.equal(missing.extraTokens,0);
 const extra=compareMathRecognizers("x=55","x=5");assert.equal(extra.extraTokens,1);assert.equal(extra.missingTokens,0);
 assert.equal(compareMathRecognizers("x=2","x=5").substitutions,1);
});
