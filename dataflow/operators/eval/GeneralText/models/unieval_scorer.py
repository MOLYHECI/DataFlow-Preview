from dataflow.core import OperatorABC
from dataflow.utils.registry import OPERATOR_REGISTRY
from dataflow.utils.storage import DataFlowStorage
from dataflow.operators.eval.GeneralText.models.UniEval.utils import convert_to_json
from dataflow.operators.eval.GeneralText.models.UniEval.metric.evaluator import get_evaluator
import torch
from tqdm import tqdm

@OPERATOR_REGISTRY.register()
class UnievalScorer(OperatorABC):
    def __init__(self, metrics_to_keep=None, device=None):
        # Initialize parameters and model
        self.metrics_to_keep = metrics_to_keep or {}
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        self.batch_size = -1
        self.score_type = float
        self.data_type = 'text'
        self.score_name = 'UnievalScore'

    @staticmethod
    def get_desc(self, lang):
        return "使用Unieval评分器评估指令质量" if lang == "zh" else "Evaluate instruction quality using the Unieval scorer."

    def evaluate_batch(self, batch):
        output_list = next(iter(batch.values()))
        results = {}

        # Fluency evaluation
        if self.metrics_to_keep.get('fluency'):
            sum_task = 'summarization'
            sum_data = convert_to_json(output_list=output_list, src_list=[''] * len(output_list), ref_list=[''] * len(output_list))
            sum_evaluator = get_evaluator(sum_task, device=self.device)
            fluency_scores = sum_evaluator.evaluate(sum_data, dims=['fluency'], print_result=False)
            results['UniEvalFluencyScore'] = [score.get('fluency', None) for score in fluency_scores]

        # Naturalness and Understandability evaluation
        if self.metrics_to_keep.get('naturalness') or self.metrics_to_keep.get('understandability'):
            dialogue_task = 'dialogue'
            dialogue_data = convert_to_json(output_list=output_list, src_list=[''] * len(output_list), context_list=[''] * len(output_list))
            dialogue_evaluator = get_evaluator(dialogue_task, device=self.device)
            dialogue_scores = dialogue_evaluator.evaluate(dialogue_data, dims=['naturalness', 'understandability'], print_result=False)

            if self.metrics_to_keep.get('naturalness'):
                results['UniEvalNaturalnessScore'] = [score.get('naturalness', None) for score in dialogue_scores]

            if self.metrics_to_keep.get('understandability'):
                results['UniEvalUnderstandabilityScore'] = [score.get('understandability', None) for score in dialogue_scores]

        return results

    def eval(self, dataframe, input_key, output_key):
        """Evaluate the scores for all rows in the dataframe."""
        scores = []
        for sample_output in tqdm(dataframe[output_key], desc="UnievalScorer Evaluating..."):
            batch = {output_key: [sample_output]}
            score = self.evaluate_batch(batch)
            scores.append(score)
        return scores

    def run(self, storage: DataFlowStorage, input_key: str, output_key: str):
        """Read the dataframe, evaluate the scores, and store the results under the output_key."""
        dataframe = storage.read("dataframe")  # Read dataframe from storage
        scores = self.eval(dataframe, input_key, output_key)  # Evaluate the scores
        
        # Flatten the results and store them under the output_key
        for score_dict in scores:
            for key, value in score_dict.items():
                if key not in dataframe:
                    dataframe[key] = []
                dataframe[key].append(value)

        storage.write(dataframe)  # Write the updated dataframe back to storage
