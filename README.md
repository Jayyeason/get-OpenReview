# The $\text{Re}^2$ dataset
### Introduction

The $\text{Re}^2$ dataset is the largest real-world consistency-ensured dataset for peer review, which features the widest range of conferences and the most complete review stages, including initial submissions, reviews, ratings and confidence, aspect ratings, rebuttals, discussions, score changes, meta-reviews, and final decisions. Our dataset is available at [Huggingface](https://huggingface.co/datasets/Daoze/ReviewRebuttal), and includes reviews, rebuttals, and papers. The `papers` section contains the latest versions of the papers before review in both `.tex` and `.md` formats. For the `.tex` files, we have filtered out the references and appendices.




### Comparison with Existing Datasets

The comparison between our proposed dataset and existing peer review datasets is given below. **Only the datasets in [bold] can guarantee all provided papers are initial submissions, which is critical for the consistency and quality of the review data.** For the “Task” column, AP is the abbreviation for Acceptance Prediction, SP for Score Prediction, RA refers to Review Analysis tasks, RG stands for Review Generation, and MG denotes Meta-review Generation. In the three columns representing numbers, “-” means please refer to the original dataset for the number.

| Dataset Name      | Data Source                                   | Task               | Reviews | Aspect Scores | Rebuttal | Score Changes | Meta-reviews | Final Decision | #Paper     | #Review Comments | #Rebuttal  |
| ----------------- | --------------------------------------------- | ------------------ | ------- | ------------- | -------- | ------------- | ------------ | -------------- | ---------- | ---------------- | ---------- |
| PeerRead          | ICLR 17, ACL 17, NeurIPS 13-17                | AP, SP             | ✓       | ✓             | ✓        | ✓             | ✓            | ✓              | 14,700     | 10,700           | 0          |
| DISAPERE          | ICLR 19-20                                    | RA                 | ✓       | ✓             | ✓        |               |              |                | 0          | 506              | 506        |
| PEERAssist        | ICLR 17-20                                    | AP                 | ✓       | ✓             |          |               |              |                | 4,467      | 13,401           | 0          |
| **[MReD]**        | **ICLR 18-21**                                | **MG**             | **✓**   | **✓**         |          | **✓**         | **✓**        | **✓**          | **7,894**  | **30,764**       | **0**      |
| ASAP-Review       | ICLR 17-20, NeurIPS 16-19                     | RG                 | ✓       | ✓             | ✓        | ✓             |              |                | 8,877      | 28,119           | 0          |
| **[NLPeer]**      | **ACL 17, ARR 22, COLING 20, CONLL 16**       | **RA**             | **✓**   | **✓**         | **✓**    | **✓**         |              |                | **5,672**  | **11,515**       | **0**      |
| PRRCA             | ICLR 17-21                                    | MG                 | ✓       | ✓             | ✓        | ✓             | ✓            | ✓              | 7,627      | 25,316           | -          |
| Zhang et al.      | ICLR 17-22                                    | RA                 | ✓       | ✓             | ✓        | ✓             | ✓            | ✓              | 10,289     | 36,453           | 68,721     |
| **[ARIES]**       | **OpenReview**                                | **RG**             | **✓**   | **✓**         | **✓**    | **✓**         | **✓**        | **✓**          | **1,720**  | **4,088**        | **0**      |
| AgentReview       | ICLR 20-23                                    | RG, MG             | ✓       | ✓             | ✓        | ✓             | ✓            | ✓              | 500        | 10,460           | -          |
| Reviewer2         | ICLR 17-23, NeurIPS 16-22 (PeerRead & NLPeer) | RG                 | ✓       | ✓             | ✓        | ✓             | ✓            | ✓              | 27,805     | 99,727           | 0          |
| RR-MCQ            | ICLR 17 (from PeerRead)                       | RG                 | ✓       | ✓             |          |               |              |                | 14         | 55               | 0          |
| ReviewMT          | ICLR 17-24                                    | RG                 | ✓       | ✓             | ✓        | ✓             | ✓            | ✓              | 26,841     | 92,017           | 0          |
| Review-5K         | ICLR 24                                       | RG                 | ✓       | ✓             | ✓        | ✓             | ✓            | ✓              | 4,991      | 16,000           | 0          |
| DeepReview-13K    | ICLR 24-25                                    | RG                 | ✓       | ✓             | ✓        | ✓             | ✓            | ✓              | 13,378     | 13,378           | 0          |
| **[Our dataset]** | **45 venues from 2017 to 2025**               | **RG, MG, AP, SP** | **✓**   | **✓**         | **✓**    | **✓**         | **✓**        | **✓**          | **19,926** | **70,668**       | **53,818** |



### Code to Generate and Evaluate the Dataset

#### Generation

The code to generate the dataset from the crawled data is given in `./code/_1_find_templates` and `./code/_2_gene_dataset`. Specifically, `_1_find_templates` contains the code to find all the templates of different conferences and years, and process them as a unified format; `_2_gene_dataset` contains the code to generate the dataset.

#### Evaluation

The code to evaluate on our test dataset is given in  `./code/_3_evaluation`. 



### Review Data Format

The format of the review data is below (with a more detailed example [here](https://anonymous.4open.science/r/ReviewBench_anon/examples/review_paper_as_sample.json)). `paper_id` refers to the unique identifier of the paper on OpenReview. `initial_score` is the score before the rebuttal, and `final_score` is the final score after the rebuttal. Fields ending with `_unified` represent the scores after unification. `review_initial_ratings_unified` and `review_final_ratings_unified` are the lists of all review scores before and after the rebuttal, respectively.


```json
[
    {
        "paper_id": "m97Cdr9IOZJ",
        "conference_year_track": "NeurIPS 2022 Conference",
        "reviews": [
            {
                "reviewer_id": "Reviewer_UuMf",
                "review_title": "null",
                "review_content": "<review_content>",
                "initial_score": {
                    "rating": "7: Accept: Technically solid paper, with high impact...",
                    "confidence": "3: You are fairly confident...",
                    "aspect_score": "soundness: 3 good\npresentation: 4 excellent\ncontribution: 3 good\n"
                },
                "final_score": {
                    "rating": "7: Accept: Technically solid paper, with high impact...",
                    "confidence": "3: You are fairly confident...",
                    "aspect_score": "soundness: 3 good\npresentation: 4 excellent\ncontribution: 3 good\n"
                },
                "initial_score_unified": {
                    "rating": "7 accept, but needs minor improvements",
                    "confidence": "The reviewer is fairly confident that the evaluation is correct"
                },
                "final_score_unified": {
                    "rating": "7 accept, but needs minor improvements",
                    "confidence": "The reviewer is fairly confident that the evaluation is correct"
                }
            },
            {
                "reviewer_id": "Reviewer_15hV",
                "review_title": "null",
                "review_content": "<review_content>",
                "initial_score": {
                    "rating": "5: Borderline accept: Technically solid paper where...",
                    "confidence": "1: Your assessment is an educated guess...",
                    "aspect_score": "soundness: 3 good\npresentation: 3 good\ncontribution: 3 good\n"
                },
                "final_score": {
                    "rating": "5: Borderline accept: Technically solid paper where...",
                    "confidence": "1: Your assessment is an educated guess...",
                    "aspect_score": "soundness: 3 good\npresentation: 3 good\ncontribution: 3 good\n"
                },
                "initial_score_unified": {
                    "rating": "5 marginally below the acceptance threshold",
                    "confidence": "The reviewer's evaluation is an educated guess"
                },
                "final_score_unified": {
                    "rating": "5 marginally below the acceptance threshold",
                    "confidence": "The reviewer's evaluation is an educated guess"
                }
            },
            {
                "reviewer_id": "Reviewer_hkZK",
                "review_title": "null",
                "review_content": "<review_content>",
                "initial_score": {
                    "rating": "7: Accept: Technically solid paper, with high impact..",
                    "confidence": "3: You are fairly confident in your assessment...",
                    "aspect_score": "soundness: 3 good\npresentation: 3 good\ncontribution: 3 good\n"
                },
                "final_score": {
                    "rating": "7: Accept: Technically solid paper, with high impact...",
                    "confidence": "3: You are fairly confident in your assessment...",
                    "aspect_score": "soundness: 3 good\npresentation: 3 good\ncontribution: 3 good\n"
                },
                "initial_score_unified": {
                    "rating": "7 accept, but needs minor improvements",
                    "confidence": "The reviewer is fairly confident that the evaluation is correct"
                },
                "final_score_unified": {
                    "rating": "7 accept, but needs minor improvements",
                    "confidence": "The reviewer is fairly confident that the evaluation is correct"
                }
            }
        ],
        "review_initial_ratings_unified": [
            7,
            5,
            7
        ],
        "review_final_ratings_unified": [
            7,
            5,
            7
        ],
        "metareview": "The paper proves universal approximation in...",
        "decision": "Accept"
    }
]
```



### Rebuttal Data

As for the rebuttal, we treat the rebuttal and discussion data as a multi-turn conversation task between reviewers and authors, which enables the training and evaluation of dynamic, interactive LLM-based reviewing assistants, offering more practical guidance for authors to self-improve their work before submission.

<img src="figs/rebuttal.jpg" alt="image-20250506163001464" style="zoom: 25%;" />

The format of the review data is below (with a more detailed example [here](https://anonymous.4open.science/r/ReviewBench_anon/examples/rebuttal_conversation_as_sample.json)) 

```json
[
    {
        "paper_id": "N-eul1pdagX",
        "conference_year_track": "ICLR 2023 Conference",
        "reviewer_id": "Reviewer_s4Ez",
        "messages": [
            {
                "role": "system",
                "content": "\nYou are an experienced academic paper reviewer. You will receive a conference paper in the field of computer science or AI. Please analyze the paper content carefully and output your review content.\nMore importantly, the author will further explain or refute the review comments you gave, and you need to further discuss with the author based on the author's response. \nThe purpose of this rebuttal and discussion is:\n- Clarification: During the review process, the reviewer (you) may not accurately understand the contribution or method of the paper due to unclear expression or misunderstanding of certain details. Through rebuttal, the author has the opportunity to clarify these misunderstandings and further illustrate the effectiveness of their innovations or methods.\n- Respond to criticisms and suggestions: The reviewer (you) may make criticisms or suggestions on the paper, and the author can use the discussion session to provide specific responses, explain why certain criticisms may not apply, or how to improve and optimize certain aspects of the paper.\nFinally, you and the author will work together to enhance the persuasiveness of the paper and improve the quality of the paper.\n"
            },
            {
                "role": "user",
                "content": "Now your reviewer ID is assigned as Reviewer_s4Ez, and the following are the paper you need to review:\n```<<N-eul1pdagX>>```"
            },
            {
                "role": "assistant",
                "content": "<review_content>"
            },
            {
                "role": "user",
                "content": "Title: Response to Reviewer s4Ez\nThank you for the extensive review. We address the questions and concerns piecewise:\n\n**Q1**: Fig. 1 - can you add some details on the sampling?\n\n**Response**: As suggested, we have now included some clarifying text..."
            },
            {
                "role": "assistant",
                "content": "Title: Post Review Discussion\nThank you for clarifying.\n\nI did not notice any changes to the text after equation 5, maybe accidentally not added?..."
            },
            {
                "role": "user",
                "content": "Title: Response to Follow-up and Post Reviewer-Discussion Update\nThank you for following up.\n\n> I did not notice any changes to the text after equation 5, maybe accidentally not added?\n\nApologies, indeed, we created this sentence, but it was not added in the upload above due to a version control error on our part..."
            },
            {
                "role": "assistant",
                "content": "It was a pleasure to engage in the above discussion with the author, which has added considerable value to this work."
            }
        ],
    }
]
```

### Read Paper Contents More Easily

After you unzip the `papers.zip` file in our HuggingFace repo, you can get all the pure text files of the provided paper contents in a folder (may named `papers/`). However, the folder `papers/` contains many sub-folders, each of which is the name of the corresponding conference, year or track, which may make it inconvenient for you to find the corresponding paper content with a `paper_id`. 

To solve this problem, you can run `./code/_2_gene_dataset/make_all_text_ln.py` script first (don't forget to change the path to your local `papers/`). This script will create soft links to all paper content files in this `papers/`, making it easier for you to access the paper content based on a `paper_id`.





