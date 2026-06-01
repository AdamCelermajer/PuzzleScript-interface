const fs = require("node:fs");
const path = require("node:path");

const inputPath = process.argv[2] || "report.json";
const outputPath = process.argv[3] || "answer.csv";

function readJson(filePath) {
  const raw = fs.readFileSync(filePath, "utf8").replace(/^\uFEFF/, "");
  return JSON.parse(raw);
}

function csvCell(value) {
  if (value === undefined || value === null) {
    return "";
  }

  const text = String(value).replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  if (/[",\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

function csvRow(values) {
  return values.map(csvCell).join(",");
}

function collectAnswerRows(report) {
  if (!Array.isArray(report.submissions)) {
    throw new Error("Expected report.json to contain a submissions array.");
  }

  const rows = [];
  for (const submission of report.submissions) {
    if (!Array.isArray(submission.responses)) {
      throw new Error(`Submission ${submission.participant_id || "(unknown)"} is missing responses.`);
    }

    for (const response of submission.responses) {
      rows.push({
        game_id: response.game_id,
        participant_id: submission.participant_id,
        submitted_at: submission.submitted_at,
        colorblind: submission.colorblind,
        game_order: response.game_order,
        screenshot_url: response.screenshot_url,
        answer_text: response.answer_text,
      });
    }
  }

  rows.sort((left, right) => {
    const byGame = String(left.game_id || "").localeCompare(String(right.game_id || ""));
    if (byGame !== 0) {
      return byGame;
    }
    return String(left.submitted_at || "").localeCompare(String(right.submitted_at || ""));
  });

  const countsByGame = new Map();
  for (const row of rows) {
    countsByGame.set(row.game_id, (countsByGame.get(row.game_id) || 0) + 1);
  }

  const seenByGame = new Map();
  return rows.map(row => {
    const answerNumber = (seenByGame.get(row.game_id) || 0) + 1;
    seenByGame.set(row.game_id, answerNumber);
    return {
      ...row,
      answer_count_for_game: countsByGame.get(row.game_id),
      answer_number_for_game: answerNumber,
    };
  });
}

function writeAnswersCsv(rows, filePath) {
  const headers = [
    "game_id",
    "answer_count_for_game",
    "answer_number_for_game",
    "participant_id",
    "submitted_at",
    "colorblind",
    "game_order",
    "screenshot_url",
    "answer_text",
  ];

  const lines = [
    csvRow(headers),
    ...rows.map(row => csvRow(headers.map(header => row[header]))),
  ];

  fs.mkdirSync(path.dirname(path.resolve(filePath)), { recursive: true });
  fs.writeFileSync(filePath, `${lines.join("\n")}\n`, "utf8");
}

const report = readJson(inputPath);
const rows = collectAnswerRows(report);
writeAnswersCsv(rows, outputPath);

console.log(`Wrote ${rows.length} answers grouped by ${new Set(rows.map(row => row.game_id)).size} games to ${outputPath}`);
