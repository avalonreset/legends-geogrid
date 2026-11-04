import bundledSample from './data/home-slice-study.json'
import bundledResearch from './data/home-slice-campaign-research.json'
import bundledNameReview from './data/home-slice-name-review.json'

const bootstrap = globalThis.__GEOGRID_BOOTSTRAP__
export const sample = bootstrap?.study || bundledSample
export const sampleResearch = bootstrap?.campaignResearch !== undefined ? bootstrap.campaignResearch : bundledResearch
export const sampleNameReview = bootstrap?.nameReview !== undefined ? bootstrap.nameReview : bundledNameReview
