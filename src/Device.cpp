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

#include "Auth.hpp"
#include "Http.hpp"
#include "Job.hpp"
#include "Metadata.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <ibm-qdmi-device/constants.h>
#include <ibm_qdmi/device.h>
#include <memory>
#include <mutex>
#include <new>
#include <nlohmann/json.hpp>
#include <nlohmann/json_fwd.hpp>
#include <optional>
#include <span>
#include <string>
#include <thread>
#include <unordered_map>
#include <utility>
#include <vector>

struct IBM_QDMI_Site_impl_d {
  std::size_t index;
};
struct IBM_QDMI_Operation_impl_d {
  std::size_t index;
};
struct IBM_QDMI_Device_Session_impl_d {
  std::mutex mutex;
  ibm::Configuration configuration;
  std::unique_ptr<ibm::Auth> auth;
  ibm::Metadata metadata;
  std::vector<std::unique_ptr<IBM_QDMI_Site_impl_d>> sites;
  std::vector<std::unique_ptr<IBM_QDMI_Operation_impl_d>> operations;
};
struct IBM_QDMI_Device_Job_impl_d {
  explicit IBM_QDMI_Device_Job_impl_d(
      std::shared_ptr<IBM_QDMI_Device_Session_impl_d> owner)
      : session(std::move(owner)),
        job(*session->auth, session->configuration.backend,
            session->metadata.sites.size()) {}
  std::timed_mutex mutex;
  std::shared_ptr<IBM_QDMI_Device_Session_impl_d> session;
  ibm::Job job;
};

namespace {
struct State {
  std::mutex mutex;
  bool initialized = false;
  std::unordered_map<IBM_QDMI_Device_Session,
                     std::shared_ptr<IBM_QDMI_Device_Session_impl_d>>
      sessions;
  std::unordered_map<IBM_QDMI_Device_Job,
                     std::shared_ptr<IBM_QDMI_Device_Job_impl_d>>
      jobs;
};
State& state() {
  static State value;
  return value;
}

template <class Function> int boundary(Function&& function) noexcept {
  try {
    return std::forward<Function>(function)();
  } catch (const ibm::Failure& error) {
    return error.status;
  } catch (const std::bad_alloc&) {
    return QDMI_ERROR_OUTOFMEM;
  } catch (...) {
    return QDMI_ERROR_FATAL;
  }
}
void require(bool condition, int status = QDMI_ERROR_INVALIDARGUMENT) {
  if (!condition) {
    throw ibm::Failure{status};
  }
}
bool validEnum(int value, int maximum) {
  return (value >= 0 && value < maximum) ||
         (value >= QDMI_DEVICE_PROPERTY_CUSTOM1 &&
          value <= QDMI_DEVICE_PROPERTY_CUSTOM5);
}
std::shared_ptr<IBM_QDMI_Device_Session_impl_d>
sessionFor(IBM_QDMI_Device_Session handle) {
  auto& registry = state();
  const std::scoped_lock lock(registry.mutex);
  const auto found = registry.sessions.find(handle);
  require(found != registry.sessions.end());
  return found->second;
}
std::shared_ptr<IBM_QDMI_Device_Job_impl_d> jobFor(IBM_QDMI_Device_Job handle) {
  auto& registry = state();
  const std::scoped_lock lock(registry.mutex);
  const auto found = registry.jobs.find(handle);
  require(found != registry.jobs.end());
  return found->second;
}
template <class Value> Value readValue(std::size_t size, const void* value) {
  require(size == sizeof(Value));
  Value result{};
  std::memcpy(&result, value, size);
  return result;
}
int copyBytes(const void* source, std::size_t required, std::size_t size,
              void* value, std::size_t* sizeRet) {
  require(value == nullptr || size >= required);
  if (sizeRet != nullptr) {
    *sizeRet = required;
  }
  if (value != nullptr && required != 0) {
    std::memcpy(value, source, required);
  }
  return QDMI_SUCCESS;
}
template <class Value>
int copyValue(const Value& source, std::size_t size, void* value,
              std::size_t* sizeRet) {
  return copyBytes(&source, sizeof(Value), size, value, sizeRet);
}
int copyString(const std::string& source, std::size_t size, void* value,
               std::size_t* sizeRet) {
  return copyBytes(source.c_str(), source.size() + 1, size, value, sizeRet);
}
template <class Value>
int copyOptional(const std::optional<Value>& source, std::size_t size,
                 void* value, std::size_t* sizeRet) {
  require(source.has_value(), QDMI_ERROR_NOTSUPPORTED);
  return copyValue(*source, size, value, sizeRet);
}
template <class Value>
int copyList(const std::vector<Value>& source, std::size_t size, void* value,
             std::size_t* sizeRet) {
  return copyBytes(static_cast<const void*>(source.data()),
                   source.size() * sizeof(Value), size, value, sizeRet);
}
std::string readString(std::size_t size, const void* value) {
  require(size != 0);
  const auto* text = static_cast<const char*>(value);
  require(text[size - 1] == '\0');
  require(std::memchr(text, '\0', size - 1) == nullptr);
  return {text, size - 1};
}
std::string resource(const IBM_QDMI_Device_Session_impl_d& session,
                     const std::string& suffix) {
  return "/v1/backends/" + session.configuration.backend + "/" + suffix;
}
std::size_t siteIndex(const IBM_QDMI_Device_Session_impl_d& session,
                      IBM_QDMI_Site site) {
  const auto found = std::ranges::find_if(
      session.sites, [site](const auto& owned) { return owned.get() == site; });
  require(found != session.sites.end());
  return (*found)->index;
}
} // namespace

int IBM_QDMI_device_initialize() {
  return boundary([] {
    auto& registry = state();
    const std::scoped_lock lock(registry.mutex);
    require(!registry.initialized, QDMI_ERROR_BADSTATE);
    registry.initialized = true;
    return QDMI_SUCCESS;
  });
}
int IBM_QDMI_device_finalize() {
  return boundary([] {
    auto& registry = state();
    const std::scoped_lock lock(registry.mutex);
    require(registry.initialized, QDMI_ERROR_BADSTATE);
    require(registry.sessions.empty() && registry.jobs.empty(),
            QDMI_ERROR_FATAL);
    registry.initialized = false;
    return QDMI_SUCCESS;
  });
}
int IBM_QDMI_device_session_alloc(IBM_QDMI_Device_Session* session) {
  return boundary([&]() -> int {
    require(session != nullptr);
    auto& registry = state();
    const std::scoped_lock lock(registry.mutex);
    require(registry.initialized, QDMI_ERROR_BADSTATE);
    auto allocated = std::make_shared<IBM_QDMI_Device_Session_impl_d>();
    auto* handle = allocated.get();
    registry.sessions.emplace(handle, std::move(allocated));
    *session = handle;
    return QDMI_SUCCESS;
  });
}
void IBM_QDMI_device_session_free(IBM_QDMI_Device_Session session) {
  // Free has no status channel. Invalid handles are harmless and never
  // dereferenced.
  (void)boundary([&]() -> int {
    auto& registry = state();
    const std::scoped_lock lock(registry.mutex);
    registry.sessions.erase(session);
    return QDMI_SUCCESS;
  });
}
int IBM_QDMI_device_session_set_parameter(
    IBM_QDMI_Device_Session handle, QDMI_Device_Session_Parameter parameter,
    std::size_t size, const void* value) {
  return boundary([&]() -> int {
    auto session = sessionFor(handle);
    const std::scoped_lock lock(session->mutex);
    require(validEnum(parameter, QDMI_DEVICE_SESSION_PARAMETER_MAX));
    require(!session->auth, QDMI_ERROR_BADSTATE);
    std::string* destination = nullptr;
    switch (parameter) {
    case QDMI_DEVICE_SESSION_PARAMETER_TOKEN:
      destination = &session->configuration.apiKey;
      break;
    case QDMI_DEVICE_SESSION_PARAMETER_BASEURL:
      destination = &session->configuration.baseUrl;
      break;
    case QDMI_DEVICE_SESSION_PARAMETER_AUTHURL:
      destination = &session->configuration.authUrl;
      break;
    case IBM_QDMI_DEVICE_SESSION_PARAMETER_BACKEND:
      destination = &session->configuration.backend;
      break;
    case IBM_QDMI_DEVICE_SESSION_PARAMETER_INSTANCE_CRN:
      destination = &session->configuration.crn;
      break;
    default:
      return QDMI_ERROR_NOTSUPPORTED;
    }
    if (value != nullptr) {
      *destination = readString(size, value);
    }
    return QDMI_SUCCESS;
  });
}
int IBM_QDMI_device_session_init(IBM_QDMI_Device_Session handle) {
  return boundary([&]() -> int {
    auto session = sessionFor(handle);
    const std::scoped_lock lock(session->mutex);
    require(!session->auth, QDMI_ERROR_BADSTATE);
    auto configuration = ibm::resolve(session->configuration);
    auto auth = std::make_unique<ibm::Auth>(configuration);
    const auto path = "/v1/backends/" + configuration.backend + "/";
    const auto config =
        nlohmann::json::parse(auth->get(path + "configuration"));
    auto properties = nlohmann::json::object();
    try {
      properties = nlohmann::json::parse(auth->get(path + "properties"));
    } catch (const ibm::Failure& error) {
      if (error.status != QDMI_ERROR_NOTFOUND) {
        throw;
      }
    }
    auto metadata = ibm::parseMetadata(config, properties);
    require(metadata.name == configuration.backend, QDMI_ERROR_FATAL);
    std::vector<std::unique_ptr<IBM_QDMI_Site_impl_d>> sites;
    std::vector<std::unique_ptr<IBM_QDMI_Operation_impl_d>> operations;
    sites.reserve(metadata.sites.size());
    operations.reserve(metadata.operations.size());
    for (std::size_t i = 0; i < metadata.sites.size(); ++i) {
      sites.push_back(std::make_unique<IBM_QDMI_Site_impl_d>(i));
    }
    for (std::size_t i = 0; i < metadata.operations.size(); ++i) {
      operations.push_back(std::make_unique<IBM_QDMI_Operation_impl_d>(i));
    }
    session->configuration = std::move(configuration);
    session->metadata = std::move(metadata);
    session->sites = std::move(sites);
    session->operations = std::move(operations);
    session->auth = std::move(auth);
    return QDMI_SUCCESS;
  });
}
int IBM_QDMI_device_session_query_device_property(
    IBM_QDMI_Device_Session handle, QDMI_Device_Property property,
    std::size_t size, void* value, std::size_t* sizeRet) {
  return boundary([&]() -> int {
    auto session = sessionFor(handle);
    const std::scoped_lock lock(session->mutex);
    require(validEnum(property, QDMI_DEVICE_PROPERTY_MAX));
    require(session->auth != nullptr, QDMI_ERROR_BADSTATE);
    const auto& metadata = session->metadata;
    switch (property) {
    case QDMI_DEVICE_PROPERTY_NAME:
      return copyString(metadata.name, size, value, sizeRet);
    case QDMI_DEVICE_PROPERTY_VERSION:
      return copyString(metadata.version, size, value, sizeRet);
    case QDMI_DEVICE_PROPERTY_LIBRARYVERSION:
      return copyString("1.3.3", size, value, sizeRet);
    case QDMI_DEVICE_PROPERTY_SUPPORTEDPROGRAMFORMATS:
      return copyValue(QDMI_PROGRAM_FORMAT_QASM3, size, value, sizeRet);
    case QDMI_DEVICE_PROPERTY_QUBITSNUM:
      return copyValue(metadata.sites.size(), size, value, sizeRet);
    case QDMI_DEVICE_PROPERTY_DURATIONUNIT:
      return copyString("ps", size, value, sizeRet);
    case QDMI_DEVICE_PROPERTY_DURATIONSCALEFACTOR:
      return copyValue(1.0, size, value, sizeRet);
    case QDMI_DEVICE_PROPERTY_SITES: {
      std::vector<IBM_QDMI_Site> sites;
      for (const auto& site : session->sites) {
        sites.push_back(site.get());
      }
      return copyList(sites, size, value, sizeRet);
    }
    case QDMI_DEVICE_PROPERTY_OPERATIONS: {
      std::vector<IBM_QDMI_Operation> operations;
      for (const auto& operation : session->operations) {
        operations.push_back(operation.get());
      }
      return copyList(operations, size, value, sizeRet);
    }
    case QDMI_DEVICE_PROPERTY_COUPLINGMAP: {
      std::vector<IBM_QDMI_Site> coupling;
      for (const auto& sites : metadata.coupling) {
        for (const auto index : sites) {
          coupling.push_back(session->sites[index].get());
        }
      }
      return copyList(coupling, size, value, sizeRet);
    }
    case QDMI_DEVICE_PROPERTY_STATUS:
    case QDMI_DEVICE_PROPERTY_QUEUELENGTH: {
      const auto status = ibm::parseStatus(nlohmann::json::parse(
          session->auth->get(resource(*session, "status"))));
      if (property == QDMI_DEVICE_PROPERTY_QUEUELENGTH) {
        return copyValue(status.queue, size, value, sizeRet);
      }
      require(status.available.has_value(), QDMI_ERROR_NOTSUPPORTED);
      auto deviceStatus = QDMI_DEVICE_STATUS_OFFLINE;
      if (*status.available) {
        deviceStatus = status.queue == 0 ? QDMI_DEVICE_STATUS_IDLE
                                         : QDMI_DEVICE_STATUS_BUSY;
      }
      return copyValue(deviceStatus, size, value, sizeRet);
    }
    default:
      return QDMI_ERROR_NOTSUPPORTED;
    }
  });
}

int IBM_QDMI_device_session_create_device_job(IBM_QDMI_Device_Session handle,
                                              IBM_QDMI_Device_Job* result) {
  return boundary([&] {
    require(result != nullptr);
    auto session = sessionFor(handle);
    const std::scoped_lock sessionLock(session->mutex);
    require(session->auth != nullptr, QDMI_ERROR_BADSTATE);
    auto allocated = std::make_shared<IBM_QDMI_Device_Job_impl_d>(session);
    auto* job = allocated.get();
    auto& registry = state();
    const std::scoped_lock lock(registry.mutex);
    registry.jobs.emplace(job, std::move(allocated));
    *result = job;
    return QDMI_SUCCESS;
  });
}
int IBM_QDMI_device_session_retrieve_device_job_by_id(
    IBM_QDMI_Device_Session handle, const char* id,
    IBM_QDMI_Device_Job* result) {
  return boundary([&] {
    require(result != nullptr && id != nullptr);
    auto session = sessionFor(handle);
    const std::scoped_lock sessionLock(session->mutex);
    require(session->auth != nullptr, QDMI_ERROR_BADSTATE);
    auto allocated = std::make_shared<IBM_QDMI_Device_Job_impl_d>(session);
    allocated->job.retrieve(id);
    auto* job = allocated.get();
    auto& registry = state();
    const std::scoped_lock lock(registry.mutex);
    registry.jobs.emplace(job, std::move(allocated));
    *result = job;
    return QDMI_SUCCESS;
  });
}
int IBM_QDMI_device_job_set_parameter(IBM_QDMI_Device_Job handle,
                                      QDMI_Device_Job_Parameter parameter,
                                      std::size_t size, const void* value) {
  return boundary([&]() -> int {
    auto owned = jobFor(handle);
    const std::scoped_lock lock(owned->mutex);
    auto& job = owned->job;
    require(validEnum(parameter, QDMI_DEVICE_JOB_PARAMETER_MAX));
    require(value == nullptr || size != 0);
    require(job.configurable(), QDMI_ERROR_BADSTATE);
    switch (parameter) {
    case QDMI_DEVICE_JOB_PARAMETER_PROGRAMFORMAT:
      if (value != nullptr) {
        const auto format = readValue<QDMI_Program_Format>(size, value);
        require(validEnum(format, QDMI_PROGRAM_FORMAT_MAX));
        require(format == QDMI_PROGRAM_FORMAT_QASM3, QDMI_ERROR_NOTSUPPORTED);
        job.format = format;
      }
      break;
    case QDMI_DEVICE_JOB_PARAMETER_PROGRAM:
      if (value != nullptr) {
        job.setProgram(readString(size, value));
      }
      break;
    case QDMI_DEVICE_JOB_PARAMETER_SHOTSNUM:
      if (value != nullptr) {
        const auto shots = readValue<std::size_t>(size, value);
        require(shots != 0);
        job.shots = shots;
      }
      break;
    case IBM_QDMI_DEVICE_JOB_PARAMETER_MAX_EXECUTION_TIME:
      if (value != nullptr) {
        const auto seconds = readValue<std::uint64_t>(size, value);
        require(seconds != 0 && seconds <= 10800);
        job.maxExecutionTime = seconds;
      }
      break;
    case IBM_QDMI_DEVICE_JOB_PARAMETER_DYNAMICAL_DECOUPLING:
      if (value != nullptr) {
        job.setDynamicalDecoupling(readString(size, value));
      }
      break;
    default:
      return QDMI_ERROR_NOTSUPPORTED;
    }
    return QDMI_SUCCESS;
  });
}
int IBM_QDMI_device_job_query_property(IBM_QDMI_Device_Job handle,
                                       QDMI_Device_Job_Property property,
                                       std::size_t size, void* value,
                                       std::size_t* sizeRet) {
  return boundary([&]() -> int {
    auto owned = jobFor(handle);
    const std::scoped_lock lock(owned->mutex);
    const auto& job = owned->job;
    require(validEnum(property, QDMI_DEVICE_JOB_PROPERTY_MAX));
    switch (property) {
    case QDMI_DEVICE_JOB_PROPERTY_ID:
      require(!job.id.empty(), QDMI_ERROR_BADSTATE);
      return copyString(job.id, size, value, sizeRet);
    case QDMI_DEVICE_JOB_PROPERTY_PROGRAMFORMAT:
      require(job.format.has_value(), QDMI_ERROR_BADSTATE);
      return copyOptional(job.format, size, value, sizeRet);
    case QDMI_DEVICE_JOB_PROPERTY_PROGRAM:
      require(!job.program.empty(), QDMI_ERROR_BADSTATE);
      return copyString(job.program, size, value, sizeRet);
    case QDMI_DEVICE_JOB_PROPERTY_SHOTSNUM:
      return copyValue(job.shots, size, value, sizeRet);
    default:
      return QDMI_ERROR_NOTSUPPORTED;
    }
  });
}
int IBM_QDMI_device_job_submit(IBM_QDMI_Device_Job handle) {
  return boundary([&] {
    auto owned = jobFor(handle);
    const std::scoped_lock lock(owned->mutex);
    owned->job.submit();
    return QDMI_SUCCESS;
  });
}
int IBM_QDMI_device_job_check(IBM_QDMI_Device_Job handle,
                              QDMI_Job_Status* status) {
  return boundary([&] {
    require(status != nullptr);
    auto owned = jobFor(handle);
    const std::scoped_lock lock(owned->mutex);
    *status = owned->job.check();
    return QDMI_SUCCESS;
  });
}
int IBM_QDMI_device_job_cancel(IBM_QDMI_Device_Job handle) {
  return boundary([&] {
    auto owned = jobFor(handle);
    const std::scoped_lock lock(owned->mutex);
    owned->job.cancel();
    return QDMI_SUCCESS;
  });
}
int IBM_QDMI_device_job_wait(IBM_QDMI_Device_Job handle, std::size_t timeout) {
  return boundary([&] {
    const auto started = std::chrono::steady_clock::now();
    const auto maximum = std::chrono::duration_cast<std::chrono::seconds>(
                             ibm::Deadline::max() - started)
                             .count();
    const auto deadline =
        timeout == 0 || std::cmp_greater_equal(timeout, maximum)
            ? ibm::Deadline::max()
            : started + std::chrono::seconds(timeout);
    auto owned = jobFor(handle);
    for (;;) {
      std::unique_lock lock(owned->mutex, std::defer_lock);
      require(lock.try_lock_until(deadline), QDMI_ERROR_TIMEOUT);
      const auto status = owned->job.check(deadline);
      require(status != QDMI_JOB_STATUS_CREATED, QDMI_ERROR_BADSTATE);
      require(status != QDMI_JOB_STATUS_FAILED, QDMI_ERROR_FATAL);
      if (ibm::terminal(status)) {
        return QDMI_SUCCESS;
      }
      lock.unlock();
      const auto now = std::chrono::steady_clock::now();
      require(now < deadline, QDMI_ERROR_TIMEOUT);
      std::this_thread::sleep_until(
          std::min(deadline, now + std::chrono::seconds{1}));
    }
  });
}
int IBM_QDMI_device_job_get_results(IBM_QDMI_Device_Job handle,
                                    QDMI_Job_Result result, std::size_t size,
                                    void* value, std::size_t* sizeRet) {
  return boundary([&]() -> int {
    auto owned = jobFor(handle);
    const std::scoped_lock lock(owned->mutex);
    require(validEnum(result, QDMI_JOB_RESULT_MAX));
    require(result == QDMI_JOB_RESULT_SHOTS ||
                result == QDMI_JOB_RESULT_HIST_KEYS ||
                result == QDMI_JOB_RESULT_HIST_VALUES,
            QDMI_ERROR_NOTSUPPORTED);
    const auto& data = owned->job.results();
    if (result == QDMI_JOB_RESULT_SHOTS) {
      return copyString(data.shots, size, value, sizeRet);
    }
    if (result == QDMI_JOB_RESULT_HIST_KEYS) {
      return copyString(data.keys, size, value, sizeRet);
    }
    return copyList(data.counts, size, value, sizeRet);
  });
}
void IBM_QDMI_device_job_free(IBM_QDMI_Device_Job handle) {
  (void)boundary([&] {
    auto& registry = state();
    const std::scoped_lock lock(registry.mutex);
    registry.jobs.erase(handle);
    return QDMI_SUCCESS;
  });
}
int IBM_QDMI_device_session_query_site_property(IBM_QDMI_Device_Session handle,
                                                IBM_QDMI_Site site,
                                                QDMI_Site_Property property,
                                                std::size_t size, void* value,
                                                std::size_t* sizeRet) {
  return boundary([&]() -> int {
    auto session = sessionFor(handle);
    const std::scoped_lock lock(session->mutex);
    require(validEnum(property, QDMI_SITE_PROPERTY_MAX));
    require(session->auth != nullptr, QDMI_ERROR_BADSTATE);
    const auto& data = session->metadata.sites[siteIndex(*session, site)];
    switch (property) {
    case QDMI_SITE_PROPERTY_INDEX:
      return copyValue(data.index, size, value, sizeRet);
    case QDMI_SITE_PROPERTY_T1:
      return copyOptional(data.t1, size, value, sizeRet);
    case QDMI_SITE_PROPERTY_T2:
      return copyOptional(data.t2, size, value, sizeRet);
    default:
      return QDMI_ERROR_NOTSUPPORTED;
    }
  });
}
int IBM_QDMI_device_session_query_operation_property(
    IBM_QDMI_Device_Session handle, IBM_QDMI_Operation operation,
    std::size_t numSites, const IBM_QDMI_Site* sites, std::size_t numParams,
    const double* params, QDMI_Operation_Property property, std::size_t size,
    void* value, std::size_t* sizeRet) {
  return boundary([&]() -> int {
    auto session = sessionFor(handle);
    const std::scoped_lock lock(session->mutex);
    require(validEnum(property, QDMI_OPERATION_PROPERTY_MAX));
    require(session->auth != nullptr, QDMI_ERROR_BADSTATE);
    const auto found = std::ranges::find_if(
        session->operations,
        [operation](const auto& owned) { return owned.get() == operation; });
    require(found != session->operations.end());
    const auto& data = session->metadata.operations[(*found)->index];
    ibm::Sites selected;
    if (sites != nullptr) {
      for (auto* const site : std::span(sites, numSites)) {
        selected.push_back(siteIndex(*session, site));
      }
      require(std::ranges::find(data.sites, selected) != data.sites.end(),
              QDMI_ERROR_NOTSUPPORTED);
    }
    if (params != nullptr) {
      require(data.parameters && numParams == *data.parameters,
              QDMI_ERROR_NOTSUPPORTED);
      for (const auto parameter : std::span(params, numParams)) {
        require(std::isfinite(parameter));
      }
    }
    switch (property) {
    case QDMI_OPERATION_PROPERTY_NAME:
      return copyString(data.name, size, value, sizeRet);
    case QDMI_OPERATION_PROPERTY_QUBITSNUM:
      return copyOptional(data.arity, size, value, sizeRet);
    case QDMI_OPERATION_PROPERTY_PARAMETERSNUM:
      return copyOptional(data.parameters, size, value, sizeRet);
    case QDMI_OPERATION_PROPERTY_SITES: {
      require(!data.sites.empty(), QDMI_ERROR_NOTSUPPORTED);
      std::vector<IBM_QDMI_Site> supported;
      for (const auto& entry : data.sites) {
        for (const auto index : entry) {
          supported.push_back(session->sites[index].get());
        }
      }
      return copyList(supported, size, value, sizeRet);
    }
    case QDMI_OPERATION_PROPERTY_DURATION:
    case QDMI_OPERATION_PROPERTY_FIDELITY: {
      const auto calibration =
          std::ranges::find_if(data.calibrations, [&](const auto& entry) {
            return entry.first == selected;
          });
      require(calibration != data.calibrations.end(), QDMI_ERROR_NOTSUPPORTED);
      if (property == QDMI_OPERATION_PROPERTY_DURATION) {
        return copyOptional(calibration->second.duration, size, value, sizeRet);
      }
      return copyOptional(calibration->second.fidelity, size, value, sizeRet);
    }
    default:
      return QDMI_ERROR_NOTSUPPORTED;
    }
  });
}
