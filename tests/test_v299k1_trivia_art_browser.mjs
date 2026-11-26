// v2.9.9k1: keep Christmas Trivia artwork selectable without changing scoring.
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {test} from "node:test";
import {fileURLToPath} from "node:url";
const source=readFileSync(fileURLToPath(new URL("../src/snowfall/platform/static/arcade-trivia-v299e.js",import.meta.url)),"utf8");

test("stage artwork and four uniquely coloured animated presents are mapped",()=>{
 assert.match(source,/v299k1\/trivia-stage\.webp/);
 assert.match(source,/\["blue","red","gold","green"\]/);
 assert.match(source,/v299k1\/trivia-answer-/);
 assert.match(source,/sprite\.complete&&sprite\.naturalWidth/);
 assert.match(source,/stageArt\.complete&&stageArt\.naturalWidth/);
});
test("gift selection remains server-authoritative and independently hit-tested",()=>{
 assert.match(source,/const index=cards\.findIndex\(card=>rectHit\(p\.x,p\.y,card\)\)/);
 assert.match(source,/void submit\(q\.options\[index\]\)/);
 assert.match(source,/const body=pending\|\|\{session_id:state\.session_id,step:state\.step,answer:value\}/);
 assert.doesNotMatch(source,/clientScore|clientCorrect/);
});
test("original art remains available if a v2.9.9k1 asset is missing",()=>{
 assert.match(source,/else if\(art\.complete&&art\.naturalWidth\)/);
 assert.match(source,/wrapped\(ctx,box\.x,box\.y,box\.w,box\.h,index,highlighted,true\)/);
});
