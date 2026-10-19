import { test } from 'node:test'
import assert from 'node:assert/strict'
import { resolveReviewAttachment, resolveStudyAttachment } from '../src/review-attachment.js'
import { observedReviewScope, caseBriefHTML } from '../src/name-review.js'
const model={evidence:{plan_sha256:'abc'},businesses:[{id:'cid:1',cid:'1',name:'One',lat:90,lng:180},{id:'cid:2',cid:'2',name:'Two'}],points:[{observations:{q1:{status:'found',items:[{id:'cid:1',rank:1}]},q2:{status:'pending',items:[{id:'cid:2',rank:1}]}}}]}
const args={model,baseURL:'http://localhost:5186/',studyURL:'/runs/example/study.json'}
const response = value => ({ok:true,status:200,headers:new Headers({'content-type':'application/json'}),json:async()=>value})
test('old study link discovers a relative study-bound review without a query attachment', async()=>{
 let requested
 const result=await resolveReviewAttachment({...args,fetcher:async(url)=>{requested=url;return response({schema:'geogrid-study-attachments/v1',study_plan_sha256:'abc',name_review:'../research/name-review.json'})}})
 assert.equal(requested,'http://localhost:5186/runs/example/study.attachments.json')
 assert.equal(result,'http://localhost:5186/runs/research/name-review.json')
})
test('campaign research follows the same study-bound manifest without a local pointer', async()=>{
 const fetcher=async()=>response({schema:'geogrid-study-attachments/v1',study_plan_sha256:'abc',name_review:'review.json',campaign_research:'../campaign-research.json'})
 assert.equal(await resolveStudyAttachment({...args,attachment:'campaign_research',fetcher}),'http://localhost:5186/runs/campaign-research.json')
 assert.equal(await resolveReviewAttachment({...args,fetcher}),'http://localhost:5186/runs/example/review.json')
 await assert.rejects(resolveStudyAttachment({...args,attachment:'arbitrary',fetcher}),/Unknown study attachment/)
 await assert.rejects(resolveStudyAttachment({...args,attachment:'campaign_research',fetcher:async()=>response({schema:'geogrid-study-attachments/v1',study_plan_sha256:'other',campaign_research:'other.json'})}),/different study/)
})
test('mismatched study and external attachments cannot be silently adopted',async()=>{
 await assert.rejects(resolveReviewAttachment({...args,fetcher:async()=>response({schema:'geogrid-study-attachments/v1',study_plan_sha256:'wrong',name_review:'data.json'})}),/different study/)
 await assert.rejects(resolveReviewAttachment({...args,explicit:'https://external.example/review.json'}),/same origin/)
 await assert.rejects(resolveReviewAttachment({...args,fetcher:async()=>response({schema:'geogrid-study-attachments/v1',study_plan_sha256:'abc',name_review:'https://external.example/review.json'})}),/same origin/)
})
test('missing attachments preserve all measured winner identities with no clean findings',async()=>{
 assert.equal(await resolveReviewAttachment({...args,fetcher:async()=>({ok:false,status:404})}),null)
 const scope=observedReviewScope(model)
 assert.equal(scope.length,1)
 assert.equal(scope[0].id,'cid:1')
 assert.equal(scope[0].status,'not_investigated')
 assert.match(caseBriefHTML(scope[0]),/research gap/)
 assert.doesNotMatch(caseBriefHTML(scope[0]),/<textarea|type="checkbox"|Import drafts|Export drafts|Save review/)
})
