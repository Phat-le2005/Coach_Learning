'use strict';
const readline=require('node:readline');
const katex=require(process.argv[2]);
readline.createInterface({input:process.stdin,crlfDelay:Infinity}).on('line',line=>{
  let result;
  try{
    const text=JSON.parse(line);
    if(typeof text!=='string'||!text.trim()||text.length>4000)throw Error('EMPTY_OR_OVERSIZE_LATEX');
    if(/\\(?:href|url|includegraphics|html|htmlClass|htmlId|htmlStyle|htmlData|def|gdef|newcommand)\b/.test(text))throw Error('UNSUPPORTED_LAYOUT_OR_MACRO_COMMAND');
    katex.renderToString(text,{throwOnError:true,trust:false,strict:'error',maxExpand:100,maxSize:20,output:'mathml'});
    result={status:'PASS',meaning:'SYNTAX_ONLY_NOT_SOURCE_OR_MATH_CORRECTNESS'};
  }catch(e){result={status:'FAIL',reason:String(e).slice(0,240)};}
  process.stdout.write(JSON.stringify(result)+'\n');
});
