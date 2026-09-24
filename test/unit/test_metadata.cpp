/*
 * Copyright (c) 2026 Munich Quantum Software Company GmbH
 * All rights reserved.
 *
 * Licensed under the Apache License v2.0 with LLVM Exceptions (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * https://llvm.org/LICENSE.txt
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
 * WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
 * License for the specific language governing permissions and limitations under
 * the License.
 *
 * SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
 */

#include "Http.hpp"
#include "Metadata.hpp"

#include <fstream>
#include <gtest/gtest.h>
#include <ibm_qdmi/constants.h>
#include <limits>
#include <nlohmann/json.hpp>
#include <nlohmann/json_fwd.hpp>
#include <utility>
#include <vector>

namespace {
nlohmann::json fixture() {
  std::ifstream input(IBM_QDMI_FIXTURE_FILE);
  return nlohmann::json::parse(input);
}
template <class Function> void expectFailure(Function&& function, int status) {
  try {
    std::forward<Function>(function)();
    FAIL() << "Expected a QDMI failure";
  } catch (const ibm::Failure& error) {
    EXPECT_EQ(error.status, status);
  }
}
} // namespace

TEST(Metadata, ConvertsUnitsAndPreservesDirectedTuples) {
  const auto data = fixture();
  const auto metadata =
      ibm::parseMetadata(data["configuration"], data["properties"]);
  ASSERT_EQ(metadata.sites.size(), 2);
  EXPECT_EQ(metadata.sites[0].t1, 100500000);
  EXPECT_EQ(metadata.sites[0].t2, 200000000);
  EXPECT_FALSE(metadata.sites[1].t1);
  EXPECT_EQ(metadata.coupling, (std::vector<ibm::Sites>{{0, 1}}));
  const auto& operation = metadata.operations[2];
  EXPECT_EQ(operation.arity, 2);
  EXPECT_EQ(operation.parameters, 0);
  EXPECT_EQ(operation.sites, (std::vector<ibm::Sites>{{0, 1}}));
  EXPECT_EQ(operation.calibrations.at({0, 1}).duration, 35556);
  EXPECT_DOUBLE_EQ(*operation.calibrations.at({0, 1}).fidelity, 0.98);
}
TEST(Metadata, MissingAndInvalidCalibrationIsNotZero) {
  auto data = fixture();
  EXPECT_FALSE(
      ibm::parseMetadata(data["configuration"], nlohmann::json::object())
          .sites[0]
          .t1);
  for (const auto value :
       {-1.0, 1e30, std::numeric_limits<double>::infinity()}) {
    data["properties"]["qubits"][0][0]["value"] = value;
    EXPECT_FALSE(ibm::parseMetadata(data["configuration"], data["properties"])
                     .sites[0]
                     .t1);
  }
  data["properties"]["qubits"][0][0] = {
      {"name", "T1"}, {"value", 1}, {"unit", "unknown"}};
  EXPECT_FALSE(ibm::parseMetadata(data["configuration"], data["properties"])
                   .sites[0]
                   .t1);
}
TEST(Metadata, RejectsInconsistentTopologyAndStatus) {
  auto data = fixture();
  data["configuration"]["coupling_map"] = {{0, 2}};
  expectFailure(
      [&] {
        (void)ibm::parseMetadata(data["configuration"], data["properties"]);
      },
      QDMI_ERROR_FATAL);
  data = fixture();
  data["properties"]["gates"][0]["qubits"] = {1, 0};
  expectFailure(
      [&] {
        (void)ibm::parseMetadata(data["configuration"], data["properties"]);
      },
      QDMI_ERROR_FATAL);
  expectFailure([] { (void)ibm::parseStatus({{"length_queue", -1}}); },
                QDMI_ERROR_FATAL);
  EXPECT_FALSE(ibm::parseStatus({{"length_queue", 0}}).available);
}

TEST(Metadata, ExposesAdvertisedMeasurementAndReset) {
  auto data = fixture();
  data["configuration"]["supported_instructions"] = {"measure", "reset",
                                                     "delay"};
  data["properties"]["qubits"][0].push_back(
      {{"name", "readout_length"}, {"value", 1.5}, {"unit", "us"}});
  data["properties"]["qubits"][0].push_back(
      {{"name", "readout_error"}, {"value", 0.03}});
  data["properties"]["qubits"][1].push_back(
      {{"name", "operational"}, {"value", false}});
  auto metadata = ibm::parseMetadata(data["configuration"], data["properties"]);
  ASSERT_EQ(metadata.operations.size(), 5);
  const auto& measurement = metadata.operations[3];
  EXPECT_EQ(measurement.name, "measure");
  EXPECT_EQ(measurement.arity, 1);
  EXPECT_EQ(measurement.parameters, 0);
  EXPECT_EQ(measurement.sites, (std::vector<ibm::Sites>{{0}}));
  ASSERT_EQ(measurement.calibrations.size(), 1);
  EXPECT_EQ(measurement.calibrations.at({0}).duration, 1500000);
  EXPECT_DOUBLE_EQ(*measurement.calibrations.at({0}).fidelity, 0.97);
  EXPECT_EQ(metadata.operations[4].name, "reset");
  EXPECT_EQ(metadata.operations[4].sites, measurement.sites);
  metadata =
      ibm::parseMetadata(data["configuration"], nlohmann::json::object());
  EXPECT_EQ(metadata.operations[3].sites.size(), 2);
  EXPECT_TRUE(metadata.operations[3].calibrations.empty());
  data["configuration"].erase("supported_instructions");
  EXPECT_EQ(ibm::parseMetadata(data["configuration"], data["properties"])
                .operations.size(),
            3);
}
TEST(Metadata, MergesRepeatedMeasurementCalibration) {
  auto data = fixture();
  data["configuration"]["supported_instructions"] = {"measure"};
  data["properties"]["qubits"][0].push_back(
      {{"name", "readout_length"}, {"value", 1.5}, {"unit", "us"}});
  data["properties"]["gates"].push_back(
      {{"gate", "measure"},
       {"qubits", {0}},
       {"parameters",
        {{{"name", "gate_length"}, {"value", 2}, {"unit", "us"}},
         {{"name", "gate_error"}, {"value", 0.03}}}}});
  const auto metadata =
      ibm::parseMetadata(data["configuration"], data["properties"]);
  const auto& measurement = metadata.operations[3];
  ASSERT_EQ(measurement.calibrations.size(), 1);
  EXPECT_EQ(measurement.calibrations.at({0}).duration, 1500000);
  EXPECT_DOUBLE_EQ(*measurement.calibrations.at({0}).fidelity, 0.97);
}

TEST(Metadata, PreservesTupleOrderAndFiltersFaultyCalibrations) {
  auto data = fixture();
  data["configuration"]["gates"][2]["coupling_map"] = {{1, 0}, {0, 1}};
  auto reverse = data["properties"]["gates"][0];
  reverse["qubits"] = {1, 0};
  data["properties"]["gates"].push_back(reverse);
  auto metadata = ibm::parseMetadata(data["configuration"], data["properties"]);
  EXPECT_EQ(metadata.operations[2].sites,
            (std::vector<ibm::Sites>{{1, 0}, {0, 1}}));
  EXPECT_EQ(metadata.operations[2].calibrations.size(), 2);
  data["properties"]["gates"][0]["parameters"].push_back(
      {{"name", "operational"}, {"value", false}});
  metadata = ibm::parseMetadata(data["configuration"], data["properties"]);
  EXPECT_EQ(metadata.operations[2].sites, (std::vector<ibm::Sites>{{1, 0}}));
  ASSERT_EQ(metadata.operations[2].calibrations.size(), 1);
  EXPECT_TRUE(metadata.operations[2].calibrations.contains({1, 0}));
}
TEST(Metadata, RejectsRepeatedGateCalibration) {
  for (const auto measurement : {false, true}) {
    auto data = fixture();
    if (measurement) {
      data["configuration"]["supported_instructions"] = {"measure"};
      data["properties"]["qubits"][0].push_back(
          {{"name", "readout_error"}, {"value", 0.03}});
      data["properties"]["gates"][0]["gate"] = "measure";
      data["properties"]["gates"][0]["qubits"] = {0};
    }
    const auto duplicate = data["properties"]["gates"][0];
    data["properties"]["gates"].push_back(duplicate);
    expectFailure(
        [&] {
          static_cast<void>(
              ibm::parseMetadata(data["configuration"], data["properties"]));
        },
        QDMI_ERROR_FATAL);
  }
}
TEST(Metadata, InvalidErrorsPreserveEarlierCalibration) {
  for (const auto& invalid :
       {nlohmann::json{}, nlohmann::json("invalid"), nlohmann::json(-0.1),
        nlohmann::json(1.1),
        nlohmann::json(std::numeric_limits<double>::infinity())}) {
    auto data = fixture();
    data["configuration"]["supported_instructions"] = {"measure"};
    data["properties"]["qubits"][0].push_back(
        {{"name", "readout_error"}, {"value", 0.03}});
    data["properties"]["qubits"][0].push_back(
        {{"name", "readout_error"}, {"value", invalid}});
    data["properties"]["gates"][0]["parameters"].push_back(
        {{"name", "gate_error"}, {"value", invalid}});
    const auto metadata =
        ibm::parseMetadata(data["configuration"], data["properties"]);
    EXPECT_DOUBLE_EQ(*metadata.operations[2].calibrations.at({0, 1}).fidelity,
                     0.98);
    EXPECT_DOUBLE_EQ(*metadata.operations[3].calibrations.at({0}).fidelity,
                     0.97);
  }
}
