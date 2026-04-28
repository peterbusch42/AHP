The Analytic Hierarchy Process (AHP) is a structured technique for organizing and analyzing complex decisions, developed by Thomas L. Saaty in the 1970s. It's particularly useful when a decision involves multiple competing criteria and alternatives, blending mathematical analysis with human psychology.

The core idea is to break down a complex decision into a hierarchy of smaller, more manageable parts, and then use a series of pairwise comparisons to determine the importance of each part.

The Steps of the AHP Method
Here is the step-by-step process of using AHP for a decision. Let's use a practical example: "Choosing the best car to buy."

Step 1: Decompose the Problem into a Hierarchy
First, you structure the problem into a hierarchy with at least three levels:

Goal: The ultimate objective. (e.g., Select the Best Car)

Criteria: The factors you will use to evaluate the alternatives. These can have sub-criteria. (e.g., Cost, Safety, Performance, Style)

Alternatives: The different choices you are considering. (e.g., Car A, Car B, Car C)

This creates a clear, top-down structure.

Step 2: Perform Pairwise Comparisons (The Core of AHP)
This is the most critical step. Instead of trying to rank all criteria at once, you compare them in pairs against the goal. For each pair, you ask: "Which of these two is more important, and by how much?"

You use a standard 1-to-9 scale to quantify your judgment:

Intensity	Definition	Explanation
1	Equal importance	Both criteria contribute equally to the objective.
3	Moderate importance	Experience and judgment slightly favor one over the other.
5	Strong importance	Experience and judgment strongly favor one over the other.
7	Very strong importance	One criterion is favored very strongly over another.
9	Extreme importance	The evidence favoring one criterion is of the highest possible order.
2, 4, 6, 8	Intermediate values	Used for compromise between two judgments.
 
Source:

You do this for all criteria and then repeat the process for all alternatives against each criterion (e.g., "For the Safety criterion, is Car A better than Car B? By how much?").

Step 3: Create Comparison Matrices and Calculate Priority Vectors
Your judgments are placed into square matrices. For example, when comparing criteria for the "Best Car" goal, the matrix would look like this:

Cost	Safety	Performance
Cost	1	3	5
Safety	1/3	1	2
Performance	1/5	1/2	1
 
Interpretation: In this matrix, Cost is moderately more important (3) than Safety and strongly more important (5) than Performance. The reciprocal values (e.g., 1/3, 1/5) are automatically filled in.

From this matrix, a mathematical process called "normalization" is used to derive the priority vector (or weights), which shows the relative importance of each criterion.

Step 4: Check for Consistency
AHP includes a crucial check to ensure your judgments aren't illogical or random. For example, if you say A is more important than B, and B is more important than C, you shouldn't then say C is more important than A.

This is measured using the Consistency Ratio (CR). A CR of 0.10 or less is generally considered acceptable. If it's higher, you should revisit and revise your pairwise judgments.

Step 5: Synthesize the Results to Get a Final Ranking
Finally, you combine the priority vectors from all your matrices. The criteria weights are multiplied by the weights of the alternatives for each criterion. This produces a final, overall score for each alternative.

The alternative with the highest overall score is, according to your own judgments, the best choice to achieve your goal.