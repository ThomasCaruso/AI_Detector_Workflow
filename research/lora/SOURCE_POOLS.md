# Candidate human-text source pools

This file identifies places to look for human prose. It does **not** approve any
specific training document. A document must still receive its own source-registry
record with `status: approved` before an excerpt can enter annotation.

The corpus should not be dominated by one agency or one formal register. These
pools are bootstrap sources for obtaining legally auditable prose while the
project also gathers user-owned, consented, or separately licensed writing.

## U.S. Geological Survey (USGS)

Useful for: science summaries, technical explanations, analytical descriptions.

Rights policy:
- https://www.usgs.gov/faqs/are-usgs-reportspublications-copyrighted
- https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits

USGS states that USGS-authored or produced data and information are considered
U.S. public domain. Individual pages/reports can still contain third-party images
or other material. For text training, approve only excerpts whose authorship and
rights are clear from the specific product.

Suggested starting collection:
- https://pubs.usgs.gov/

## National Institute of Standards and Technology (NIST)

Useful for: technical explanations, recommendations, practice guides, concise
analytical writing.

Rights policy:
- https://www.nist.gov/nist-research-library/library-faqs
- https://www.nist.gov/nist-research-library/nist-publications
- https://www.nist.gov/copyrights-disclaimers

NIST states that works authored by NIST employees generally are not subject to
U.S. copyright protection. Some NIST publications are written by third parties
and can be copyrighted, so approve documents individually rather than treating
all NIST-hosted material as automatically usable.

Suggested starting collection:
- https://www.nist.gov/nist-research-library/nist-publications

## U.S. Government Accountability Office (GAO)

Useful for: business/economic analysis, executive analytical prose, policy
argument, concise findings and recommendations.

Rights policy:
- https://www.gao.gov/copyright

GAO states that its products and website information are not protected by U.S.
copyright law and may be copied and distributed, while also warning that its
products can contain third-party copyrighted material. Approve the exact text
being excerpted and avoid embedded third-party quotations.

Suggested starting collection:
- https://www.gao.gov/reports-testimonies

## User-owned and consented writing

Useful for: professional email, business analysis, personal analytical voice, and
registers that public-agency prose underrepresents.

This is the preferred way to keep the corpus from becoming a government-writing
adapter. Only include text when ownership/consent is explicit and recorded in the
source registry. Do not include confidential employer/client material, personal
data, or text the contributor does not have the right to provide for training.

## Sampling policy

Before training, the corpus report should show:

- examples and words by genre;
- examples and words by provenance kind;
- examples and words by source document;
- the largest source-document share;
- train/dev/holdout counts;
- duplicate and near-duplicate audit results.

No one source document should dominate a split. Source caps belong in corpus
construction, not in model-training hyperparameters.
