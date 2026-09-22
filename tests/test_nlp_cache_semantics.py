import sys
import types
import unittest
from unittest.mock import MagicMock, patch


class FakeList(list):
    def tolist(self):
        return list(self)


class FakeSeries:
    def __init__(self, values, index):
        self.index = list(index)
        self.values = dict(zip(self.index, values))

    def apply(self, function):
        return FakeSeries(
            [function(self.values[idx]) for idx in self.index],
            self.index,
        )

    def unique(self):
        unique_values = []
        for idx in self.index:
            value = self.values[idx]
            if value not in unique_values:
                unique_values.append(value)
        return FakeList(unique_values)

    def to_dict(self):
        return {idx: self.values[idx] for idx in self.index}

    def __ge__(self, other):
        return FakeMask(
            [self.values[idx] >= other for idx in self.index],
            self.index,
        )

    def __le__(self, other):
        return FakeMask(
            [self.values[idx] <= other for idx in self.index],
            self.index,
        )


class FakeMask(FakeSeries):
    def __and__(self, other):
        if self.index != other.index:
            raise AssertionError("mask indices must match")
        return FakeMask(
            [self.values[idx] and other.values[idx] for idx in self.index],
            self.index,
        )


class FakeAtIndexer:
    def __init__(self, dataframe):
        self.dataframe = dataframe

    def __getitem__(self, key):
        idx, column = key
        return self.dataframe.rows[idx][column]

    def __setitem__(self, key, value):
        idx, column = key
        if column not in self.dataframe.columns:
            self.dataframe.columns.append(column)
        self.dataframe.rows[idx][column] = value


class FakeLocIndexer:
    def __init__(self, dataframe):
        self.dataframe = dataframe

    def __setitem__(self, key, values):
        mask, column = key
        if column not in self.dataframe.columns:
            self.dataframe.columns.append(column)
        for idx in mask.index:
            if mask.values[idx]:
                self.dataframe.rows[idx][column] = values.values[idx]


class FakeDataFrame:
    def __init__(self, data=None, index=None, columns=None):
        data = {} if data is None else data
        if data:
            lengths = {len(values) for values in data.values()}
            if len(lengths) != 1:
                raise ValueError("column lengths must match")
            row_count = lengths.pop()
        else:
            row_count = 0

        self.index = list(range(row_count)) if index is None else list(index)
        if len(self.index) != row_count:
            raise ValueError("index length must match row count")
        self.columns = list(columns) if columns is not None else list(data)
        self.rows = {
            idx: {column: data[column][position] for column in data}
            for position, idx in enumerate(self.index)
        }
        self.at = FakeAtIndexer(self)
        self.loc = FakeLocIndexer(self)

    @classmethod
    def from_rows(cls, source, indices):
        dataframe = cls()
        dataframe.index = list(indices)
        dataframe.columns = list(source.columns)
        dataframe.rows = {
            idx: dict(source.rows[idx])
            for idx in dataframe.index
        }
        dataframe.at = FakeAtIndexer(dataframe)
        dataframe.loc = FakeLocIndexer(dataframe)
        return dataframe

    @property
    def empty(self):
        return not self.index

    def __len__(self):
        return len(self.index)

    def __getitem__(self, key):
        if isinstance(key, str):
            return FakeSeries(
                [self.rows[idx][key] for idx in self.index],
                self.index,
            )
        if isinstance(key, FakeMask):
            selected = [idx for idx in key.index if key.values[idx]]
            return FakeDataFrame.from_rows(self, selected)
        raise TypeError(f"unsupported key: {key!r}")

    def __setitem__(self, column, values):
        if column not in self.columns:
            self.columns.append(column)
        if isinstance(values, FakeSeries):
            for idx in self.index:
                self.rows[idx][column] = values.values[idx]
            return
        for idx, value in zip(self.index, values):
            self.rows[idx][column] = value

    def apply(self, function, axis=0):
        if axis != 1:
            raise AssertionError("only row-wise apply is supported")
        return FakeSeries(
            [function(self.rows[idx]) for idx in self.index],
            self.index,
        )


def dependency_module(name, **attributes):
    module = types.ModuleType(name)
    for attribute, value in attributes.items():
        setattr(module, attribute, value)
    return module


fake_pandas = dependency_module(
    "pandas",
    DataFrame=FakeDataFrame,
    isna=lambda value: value is None,
)
fake_jieba = dependency_module(
    "jieba",
    add_word=MagicMock(),
    lcut=lambda text: [text],
)
fake_snownlp = dependency_module(
    "snownlp",
    SnowNLP=type("SnowNLP", (), {}),
)
fake_genai = dependency_module(
    "google.generativeai",
    configure=MagicMock(),
    GenerativeModel=MagicMock(),
    GenerationConfig=MagicMock(),
)
fake_google = dependency_module("google", generativeai=fake_genai)
fake_dotenv = dependency_module("dotenv", load_dotenv=MagicMock())

dependency_stubs = {
    "pandas": fake_pandas,
    "jieba": fake_jieba,
    "snownlp": fake_snownlp,
    "google": fake_google,
    "google.generativeai": fake_genai,
    "dotenv": fake_dotenv,
}

with patch.dict(sys.modules, dependency_stubs):
    sys.modules.pop("src.transform.nlp_processor", None)
    from src.transform.nlp_processor import NLPProcessor


class CacheSemanticsTests(unittest.TestCase):
    def make_processor(self, snow_scores, llm_results=None):
        processor = NLPProcessor.__new__(NLPProcessor)
        processor._calc_snownlp = MagicMock(side_effect=snow_scores)
        processor._batch_llm_api = MagicMock(
            return_value={} if llm_results is None else llm_results
        )
        return processor

    @staticmethod
    def make_writer(cache_result):
        writer = MagicMock()
        writer.fetch_cached_scores.return_value = cache_result
        return writer

    def test_cached_neutral_and_zero_scores_are_hits_without_llm(self):
        titles = ["zero", "low-neutral", "neutral", "high-neutral"]
        dataframe = FakeDataFrame(
            {"article_id": [1, 2, 3, 4], "title": titles},
            index=[10, 20, 30, 40],
        )
        processor = self.make_processor([0.5, 0.5, 0.5, 0.5])
        writer = self.make_writer(
            {
                "zero": 0.0,
                "low-neutral": 0.45,
                "neutral": 0.5,
                "high-neutral": 0.55,
            }
        )

        result = processor.process_batch_hybrid(dataframe, writer)

        self.assertIs(result, dataframe)
        writer.fetch_cached_scores.assert_called_once_with(titles)
        processor._batch_llm_api.assert_not_called()
        writer.upsert_sentiment_cache.assert_not_called()
        self.assertEqual(
            [result.at[idx, "sentiment_score"] for idx in result.index],
            [0.0, 0.45, 0.5, 0.55],
        )

    def test_mixed_batch_sends_only_original_fuzzy_cache_misses_to_llm(self):
        dataframe = FakeDataFrame(
            {
                "article_id": [1, 2, 3, 4],
                "title": ["cached", "non-fuzzy", "miss-a", "miss-b"],
            },
            index=[101, 102, 103, 104],
        )
        original_columns = list(dataframe.columns)
        original_index = list(dataframe.index)
        processor = self.make_processor(
            [0.5, 0.2, 0.55, 0.6],
            llm_results={103: 0.8, 104: 0.1},
        )
        writer = self.make_writer({"cached": 0.45})

        result = processor.process_batch_hybrid(dataframe, writer)

        writer.fetch_cached_scores.assert_called_once_with(
            ["cached", "miss-a", "miss-b"]
        )
        processor._batch_llm_api.assert_called_once_with(
            {103: "miss-a", 104: "miss-b"}
        )
        self.assertEqual(result.at[101, "sentiment_score"], 0.45)
        self.assertEqual(result.at[102, "sentiment_score"], 0.2)
        self.assertEqual(result.at[103, "sentiment_score"], 0.8)
        self.assertEqual(result.at[104, "sentiment_score"], 0.1)
        self.assertEqual(list(result.index), original_index)
        self.assertEqual(len(result), 4)
        self.assertEqual(result.columns, original_columns + ["sentiment_score"])

    def test_cached_duplicate_title_applies_to_every_fuzzy_row(self):
        dataframe = FakeDataFrame(
            {"article_id": [1, 2], "title": ["same", "same"]},
            index=[7, 9],
        )
        processor = self.make_processor([0.5, 0.55])
        writer = self.make_writer({"same": 0.5})

        result = processor.process_batch_hybrid(dataframe, writer)

        writer.fetch_cached_scores.assert_called_once_with(["same"])
        processor._batch_llm_api.assert_not_called()
        self.assertEqual(result.at[7, "sentiment_score"], 0.5)
        self.assertEqual(result.at[9, "sentiment_score"], 0.5)

    def test_duplicate_cache_miss_preserves_per_row_llm_identity(self):
        dataframe = FakeDataFrame(
            {"article_id": [1, 2], "title": ["same", "same"]},
            index=[7, 9],
        )
        processor = self.make_processor(
            [0.5, 0.55],
            llm_results={7: 0.7, 9: 0.3},
        )
        writer = self.make_writer({})

        processor.process_batch_hybrid(dataframe, writer)

        writer.fetch_cached_scores.assert_called_once_with(["same"])
        processor._batch_llm_api.assert_called_once_with(
            {7: "same", 9: "same"}
        )

    def test_legitimate_empty_cache_mapping_sends_all_fuzzy_rows_to_llm(self):
        dataframe = FakeDataFrame(
            {"article_id": [1, 2], "title": ["first", "second"]},
            index=[1, 2],
        )
        processor = self.make_processor(
            [0.45, 0.6],
            llm_results={1: 0.2, 2: 0.8},
        )
        writer = self.make_writer({})

        processor.process_batch_hybrid(dataframe, writer)

        processor._batch_llm_api.assert_called_once_with(
            {1: "first", 2: "second"}
        )

    def test_cache_read_exception_propagates_without_llm_or_cache_write(self):
        dataframe = FakeDataFrame(
            {"article_id": [1], "title": ["fuzzy"]},
            index=[1],
        )
        processor = self.make_processor([0.5])
        writer = MagicMock()
        writer.fetch_cached_scores.side_effect = RuntimeError("cache read failed")

        with self.assertRaisesRegex(RuntimeError, "cache read failed"):
            processor.process_batch_hybrid(dataframe, writer)

        processor._batch_llm_api.assert_not_called()
        writer.upsert_sentiment_cache.assert_not_called()

    def test_non_fuzzy_rows_skip_cache_and_llm(self):
        dataframe = FakeDataFrame(
            {"article_id": [1, 2], "title": ["negative", "positive"]},
            index=[3, 4],
        )
        processor = self.make_processor([0.2, 0.8])
        writer = MagicMock()

        result = processor.process_batch_hybrid(dataframe, writer)

        self.assertIs(result, dataframe)
        writer.fetch_cached_scores.assert_not_called()
        processor._batch_llm_api.assert_not_called()
        writer.upsert_sentiment_cache.assert_not_called()
        self.assertEqual(
            [result.at[idx, "sentiment_score"] for idx in result.index],
            [0.2, 0.8],
        )

    def test_empty_and_missing_title_inputs_are_unchanged_no_ops(self):
        processor = self.make_processor([])
        writer = MagicMock()
        empty = FakeDataFrame(columns=["article_id", "title"])
        missing_title = FakeDataFrame({"article_id": [1]}, index=[5])

        self.assertIs(processor.process_batch_hybrid(empty, writer), empty)
        self.assertIs(
            processor.process_batch_hybrid(missing_title, writer),
            missing_title,
        )
        self.assertEqual(empty.columns, ["article_id", "title"])
        self.assertEqual(missing_title.columns, ["article_id"])
        writer.fetch_cached_scores.assert_not_called()
        processor._batch_llm_api.assert_not_called()
        writer.upsert_sentiment_cache.assert_not_called()


if __name__ == "__main__":
    unittest.main()
