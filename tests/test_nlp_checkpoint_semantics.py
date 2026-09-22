import importlib
import io
import json
import math
import sys
import types
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

from test_nlp_cache_semantics import (
    FakeDataFrame,
    dependency_module,
    dependency_stubs,
)


with patch.dict(sys.modules, dependency_stubs):
    sys.modules.pop("src.transform.nlp_processor", None)
    nlp_module = importlib.import_module("src.transform.nlp_processor")

NLPProcessor = nlp_module.NLPProcessor


def class_module(module_name, class_name, class_value=None):
    module = types.ModuleType(module_name)
    setattr(
        module,
        class_name,
        class_value if class_value is not None else type(class_name, (), {}),
    )
    return module


pipeline_stubs = {
    "src.extractors.twse_scraper": class_module(
        "src.extractors.twse_scraper", "TwseScraper"
    ),
    "src.extractors.yfinance_api": class_module(
        "src.extractors.yfinance_api", "YFinanceAPI"
    ),
    "src.extractors.ptt_scraper": class_module(
        "src.extractors.ptt_scraper", "PttScraper"
    ),
    "src.extractors.trend_discover": class_module(
        "src.extractors.trend_discover", "TrendDiscover"
    ),
    "src.transform.data_cleaner": class_module(
        "src.transform.data_cleaner", "DataCleaner"
    ),
    "src.transform.nlp_processor": class_module(
        "src.transform.nlp_processor", "NLPProcessor", NLPProcessor
    ),
    "src.transform.feature_aggregator": class_module(
        "src.transform.feature_aggregator", "FeatureAggregator"
    ),
    "src.loaders.db_writer": class_module(
        "src.loaders.db_writer", "DBWriter"
    ),
}
# main_etl_pipeline.py 自 UG-G2-SB2 起額外 import PttSourceUnavailableError；
# 上方 ptt_scraper 隔離 stub 只建立了 PttScraper，這裡補上同名例外類別。
pipeline_stubs["src.extractors.ptt_scraper"].PttSourceUnavailableError = type(
    "PttSourceUnavailableError", (Exception,), {}
)
# §0.5 #31：main_etl_pipeline.py 額外 import GeminiDailyQuotaExhausted；
# 上方 nlp_processor 隔離 stub 只建立了 NLPProcessor，這裡補上同一個
# （已真實匯入的）例外類別，避免 pipeline_module 匯入時 ImportError。
pipeline_stubs["src.transform.nlp_processor"].GeminiDailyQuotaExhausted = (
    nlp_module.GeminiDailyQuotaExhausted
)

with patch.dict(sys.modules, pipeline_stubs):
    sys.modules.pop("main_etl_pipeline", None)
    pipeline_module = importlib.import_module("main_etl_pipeline")

ETLPipelineManager = pipeline_module.ETLPipelineManager


class StrictCompletionTests(unittest.TestCase):
    @staticmethod
    def dataframe(titles, indices=None):
        if indices is None:
            indices = list(range(1, len(titles) + 1))
        return FakeDataFrame(
            {
                "article_id": list(range(1, len(titles) + 1)),
                "title": list(titles),
            },
            index=indices,
        )

    @staticmethod
    def processor(snow_scores, api_key="test-key"):
        processor = NLPProcessor.__new__(NLPProcessor)
        processor.api_key = api_key
        processor.model = MagicMock()
        processor._calc_snownlp = MagicMock(side_effect=snow_scores)
        return processor

    @staticmethod
    def writer(cache=None):
        writer = MagicMock()
        writer.fetch_cached_scores.return_value = {} if cache is None else cache
        return writer

    def assert_dataframe_unmutated(self, dataframe, original_columns, original_rows):
        self.assertEqual(dataframe.columns, original_columns)
        self.assertEqual(dataframe.rows, original_rows)

    def test_unexpected_snownlp_exception_propagates_without_writes(self):
        dataframe = self.dataframe(["broken"])
        original_columns = list(dataframe.columns)
        original_rows = {idx: dict(row) for idx, row in dataframe.rows.items()}
        processor = NLPProcessor.__new__(NLPProcessor)
        processor.api_key = None
        processor.model = MagicMock()
        writer = self.writer()

        with patch.object(
            nlp_module.jieba,
            "lcut",
            side_effect=RuntimeError("SnowNLP failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "SnowNLP failed"):
                processor.process_batch_hybrid(dataframe, writer)

        writer.fetch_cached_scores.assert_not_called()
        writer.upsert_sentiment_cache.assert_not_called()
        self.assert_dataframe_unmutated(dataframe, original_columns, original_rows)

    def test_missing_api_key_fails_fuzzy_cache_miss_without_writes(self):
        dataframe = self.dataframe(["fuzzy"])
        original_columns = list(dataframe.columns)
        original_rows = {idx: dict(row) for idx, row in dataframe.rows.items()}
        processor = self.processor([0.5], api_key=None)
        writer = self.writer()

        with self.assertRaises((RuntimeError, ValueError)):
            processor.process_batch_hybrid(dataframe, writer)

        processor.model.generate_content.assert_not_called()
        writer.upsert_sentiment_cache.assert_not_called()
        self.assert_dataframe_unmutated(dataframe, original_columns, original_rows)

    def test_gemini_exception_propagates_without_writes(self):
        dataframe = self.dataframe(["fuzzy"])
        original_columns = list(dataframe.columns)
        original_rows = {idx: dict(row) for idx, row in dataframe.rows.items()}
        processor = self.processor([0.5])
        processor.model.generate_content.side_effect = RuntimeError("Gemini failed")
        writer = self.writer()

        with patch.object(nlp_module.time, "sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "Gemini failed"):
                processor.process_batch_hybrid(dataframe, writer)

        sleep.assert_called_once_with(4)
        writer.upsert_sentiment_cache.assert_not_called()
        self.assert_dataframe_unmutated(dataframe, original_columns, original_rows)

    def test_malformed_json_wrong_top_type_and_duplicate_keys_fail(self):
        invalid_responses = (
            "{not-json",
            "[]",
            '{"1": 0.5, "1": 0.6}',
        )

        for response_text in invalid_responses:
            with self.subTest(response=response_text):
                dataframe = self.dataframe(["fuzzy"])
                original_columns = list(dataframe.columns)
                original_rows = {
                    idx: dict(row) for idx, row in dataframe.rows.items()
                }
                processor = self.processor([0.5])
                processor.model.generate_content.return_value.text = response_text
                writer = self.writer()

                with patch.object(nlp_module.time, "sleep"):
                    with self.assertRaises((TypeError, ValueError)):
                        processor.process_batch_hybrid(dataframe, writer)

                writer.upsert_sentiment_cache.assert_not_called()
                self.assert_dataframe_unmutated(
                    dataframe, original_columns, original_rows
                )

    def test_partial_extra_and_unmappable_id_sets_fail_before_mutation(self):
        invalid_responses = (
            '{"1": 0.5}',
            '{"1": 0.5, "2": 0.6, "3": 0.7}',
            '{"1": 0.5, "02": 0.6}',
        )

        for response_text in invalid_responses:
            with self.subTest(response=response_text):
                dataframe = self.dataframe(["first", "second"], [1, 2])
                original_columns = list(dataframe.columns)
                original_rows = {
                    idx: dict(row) for idx, row in dataframe.rows.items()
                }
                processor = self.processor([0.5, 0.55])
                processor.model.generate_content.return_value.text = response_text
                writer = self.writer()

                with patch.object(nlp_module.time, "sleep"):
                    with self.assertRaises((TypeError, ValueError)):
                        processor.process_batch_hybrid(dataframe, writer)

                writer.upsert_sentiment_cache.assert_not_called()
                self.assert_dataframe_unmutated(
                    dataframe, original_columns, original_rows
                )

    def test_invalid_score_values_fail_before_any_partial_result_is_applied(self):
        invalid_scores = (
            "0.5",
            True,
            None,
            math.nan,
            math.inf,
            -math.inf,
            -0.01,
            1.01,
        )

        for invalid_score in invalid_scores:
            with self.subTest(score=invalid_score):
                dataframe = self.dataframe(["valid-first", "invalid-second"], [1, 2])
                original_columns = list(dataframe.columns)
                original_rows = {
                    idx: dict(row) for idx, row in dataframe.rows.items()
                }
                processor = self.processor([0.5, 0.5])
                processor.model.generate_content.return_value.text = json.dumps(
                    {"1": 0.8, "2": invalid_score}
                )
                writer = self.writer()

                with patch.object(nlp_module.time, "sleep"):
                    with self.assertRaises((TypeError, ValueError)):
                        processor.process_batch_hybrid(dataframe, writer)

                writer.upsert_sentiment_cache.assert_not_called()
                self.assert_dataframe_unmutated(
                    dataframe, original_columns, original_rows
                )

    def test_complete_response_including_half_validates_before_cache_and_dataframe(self):
        dataframe = self.dataframe(["neutral", "positive"], [11, 12])
        processor = self.processor([0.5, 0.55])
        processor.model.generate_content.return_value.text = (
            '{"11": 0.5, "12": 1.0}'
        )
        writer = self.writer()

        def assert_cache_write_after_validation(records):
            self.assertNotIn("sentiment_score", dataframe.columns)
            self.assertEqual(records, [("neutral", 0.5), ("positive", 1.0)])

        writer.upsert_sentiment_cache.side_effect = assert_cache_write_after_validation

        with patch.object(nlp_module.time, "sleep"):
            result = processor.process_batch_hybrid(dataframe, writer)

        writer.upsert_sentiment_cache.assert_called_once_with(
            [("neutral", 0.5), ("positive", 1.0)]
        )
        self.assertEqual(result.at[11, "sentiment_score"], 0.5)
        self.assertEqual(result.at[12, "sentiment_score"], 1.0)

    def test_mixed_non_fuzzy_cache_hit_and_gemini_rows_keep_id_mapping(self):
        dataframe = self.dataframe(
            ["non-fuzzy", "cached", "gemini-a", "gemini-b"],
            [20, 21, 22, 23],
        )
        processor = self.processor([0.2, 0.5, 0.45, 0.6])
        processor._batch_llm_api = MagicMock(return_value={22: 0.5, 23: 0.9})
        writer = self.writer({"cached": 0.55})

        result = processor.process_batch_hybrid(dataframe, writer)

        processor._batch_llm_api.assert_called_once_with(
            {22: "gemini-a", 23: "gemini-b"}
        )
        writer.upsert_sentiment_cache.assert_called_once_with(
            [("gemini-a", 0.5), ("gemini-b", 0.9)]
        )
        self.assertEqual(
            [result.at[idx, "sentiment_score"] for idx in result.index],
            [0.2, 0.55, 0.5, 0.9],
        )

    def test_cache_write_failure_propagates_before_dataframe_checkpoint(self):
        dataframe = self.dataframe(["fuzzy"])
        original_columns = list(dataframe.columns)
        original_rows = {idx: dict(row) for idx, row in dataframe.rows.items()}
        processor = self.processor([0.5])
        processor._batch_llm_api = MagicMock(return_value={1: 0.5})
        writer = self.writer()
        writer.upsert_sentiment_cache.side_effect = RuntimeError("cache write failed")

        with self.assertRaisesRegex(RuntimeError, "cache write failed"):
            processor.process_batch_hybrid(dataframe, writer)

        self.assert_dataframe_unmutated(dataframe, original_columns, original_rows)

    def test_orchestrator_processor_failure_performs_no_article_update_or_retry(self):
        dataframe = self.dataframe(["first", "second"], [1, 2])
        processor = self.processor([0.5, 0.5])
        processor.model.generate_content.return_value.text = '{"1": 0.5}'
        writer = self.writer()
        writer.fetch_data.side_effect = [
            dataframe,
            AssertionError("processor failure must not retry"),
        ]
        pipeline = ETLPipelineManager.__new__(ETLPipelineManager)
        pipeline.db_writer = writer
        pipeline.nlp_processor = processor

        with redirect_stdout(io.StringIO()):
            with patch.object(nlp_module.time, "sleep"):
                with self.assertRaises((TypeError, ValueError)):
                    pipeline.run_nlp_sentiment_pipeline()

        writer.fetch_data.assert_called_once()
        writer.upsert_sentiment_cache.assert_not_called()
        writer.update_sentiment_scores.assert_not_called()

    def test_orchestrator_updates_articles_only_after_complete_success(self):
        dataframe = self.dataframe(["neutral"], [1])
        empty = FakeDataFrame(columns=["article_id", "title"])
        processor = self.processor([0.5])
        processor.model.generate_content.return_value.text = '{"1": 0.5}'
        writer = self.writer()
        writer.fetch_data.side_effect = [dataframe, empty]
        pipeline = ETLPipelineManager.__new__(ETLPipelineManager)
        pipeline.db_writer = writer
        pipeline.nlp_processor = processor

        with redirect_stdout(io.StringIO()):
            with patch.object(nlp_module.time, "sleep"):
                pipeline.run_nlp_sentiment_pipeline()

        writer.upsert_sentiment_cache.assert_called_once_with([("neutral", 0.5)])
        writer.update_sentiment_scores.assert_called_once_with(dataframe)
        self.assertEqual(dataframe.at[1, "sentiment_score"], 0.5)


if __name__ == "__main__":
    unittest.main()
