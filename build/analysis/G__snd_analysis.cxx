// Do NOT change. Changes will be lost next time file is generated

#define R__DICTIONARY_FILENAME G__snd_analysis
#define R__NO_DEPRECATION

/*******************************************************************/
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#define G__DICTIONARY
#include "ROOT/RConfig.hxx"
#include "TClass.h"
#include "TDictAttributeMap.h"
#include "TInterpreter.h"
#include "TROOT.h"
#include "TBuffer.h"
#include "TMemberInspector.h"
#include "TInterpreter.h"
#include "TVirtualMutex.h"
#include "TError.h"

#ifndef G__ROOT
#define G__ROOT
#endif

#include "RtypesImp.h"
#include "TIsAProxy.h"
#include "TFileMergeInfo.h"
#include <algorithm>
#include "TCollectionProxyInfo.h"
/*******************************************************************/

#include "TDataMember.h"

// Header files passed as explicit arguments
#include "DataManager.h"

// Header files passed via #pragma extra_include

// The generated code does not explicitly qualify STL entities
namespace std {} using namespace std;

namespace snd {
   namespace ROOTDict {
      inline ::ROOT::TGenericClassInfo *GenerateInitInstance();
      static TClass *snd_Dictionary();

      // Function generating the singleton type initializer
      inline ::ROOT::TGenericClassInfo *GenerateInitInstance()
      {
         static ::ROOT::TGenericClassInfo 
            instance("snd", 0 /*version*/, "DataManager.h", 19,
                     ::ROOT::Internal::DefineBehavior((void*)nullptr,(void*)nullptr),
                     &snd_Dictionary, 0);
         return &instance;
      }
      // Insure that the inline function is _not_ optimized away by the compiler
      ::ROOT::TGenericClassInfo *(*_R__UNIQUE_DICT_(InitFunctionKeeper))() = &GenerateInitInstance;  
      // Static variable to force the class initialization
      static ::ROOT::TGenericClassInfo *_R__UNIQUE_DICT_(Init) = GenerateInitInstance(); R__UseDummy(_R__UNIQUE_DICT_(Init));

      // Dictionary for non-ClassDef classes
      static TClass *snd_Dictionary() {
         return GenerateInitInstance()->GetClass();
      }

   }
}

namespace ROOT {
   static void *new_sndcLcLDataManager(void *p = nullptr);
   static void *newArray_sndcLcLDataManager(Long_t size, void *p);
   static void delete_sndcLcLDataManager(void *p);
   static void deleteArray_sndcLcLDataManager(void *p);
   static void destruct_sndcLcLDataManager(void *p);

   // Function generating the singleton type initializer
   static TGenericClassInfo *GenerateInitInstanceLocal(const ::snd::DataManager*)
   {
      ::snd::DataManager *ptr = nullptr;
      static ::TVirtualIsAProxy* isa_proxy = new ::TInstrumentedIsAProxy< ::snd::DataManager >(nullptr);
      static ::ROOT::TGenericClassInfo 
         instance("snd::DataManager", ::snd::DataManager::Class_Version(), "DataManager.h", 23,
                  typeid(::snd::DataManager), ::ROOT::Internal::DefineBehavior(ptr, ptr),
                  &::snd::DataManager::Dictionary, isa_proxy, 4,
                  sizeof(::snd::DataManager) );
      instance.SetNew(&new_sndcLcLDataManager);
      instance.SetNewArray(&newArray_sndcLcLDataManager);
      instance.SetDelete(&delete_sndcLcLDataManager);
      instance.SetDeleteArray(&deleteArray_sndcLcLDataManager);
      instance.SetDestructor(&destruct_sndcLcLDataManager);
      return &instance;
   }
   TGenericClassInfo *GenerateInitInstance(const ::snd::DataManager*)
   {
      return GenerateInitInstanceLocal(static_cast<::snd::DataManager*>(nullptr));
   }
   // Static variable to force the class initialization
   static ::ROOT::TGenericClassInfo *_R__UNIQUE_DICT_(Init) = GenerateInitInstanceLocal(static_cast<const ::snd::DataManager*>(nullptr)); R__UseDummy(_R__UNIQUE_DICT_(Init));
} // end of namespace ROOT

namespace snd {
//______________________________________________________________________________
atomic_TClass_ptr DataManager::fgIsA(nullptr);  // static to hold class pointer

//______________________________________________________________________________
const char *DataManager::Class_Name()
{
   return "snd::DataManager";
}

//______________________________________________________________________________
const char *DataManager::ImplFileName()
{
   return ::ROOT::GenerateInitInstanceLocal((const ::snd::DataManager*)nullptr)->GetImplFileName();
}

//______________________________________________________________________________
int DataManager::ImplFileLine()
{
   return ::ROOT::GenerateInitInstanceLocal((const ::snd::DataManager*)nullptr)->GetImplFileLine();
}

//______________________________________________________________________________
TClass *DataManager::Dictionary()
{
   fgIsA = ::ROOT::GenerateInitInstanceLocal((const ::snd::DataManager*)nullptr)->GetClass();
   return fgIsA;
}

//______________________________________________________________________________
TClass *DataManager::Class()
{
   if (!fgIsA.load()) { R__LOCKGUARD(gInterpreterMutex); fgIsA = ::ROOT::GenerateInitInstanceLocal((const ::snd::DataManager*)nullptr)->GetClass(); }
   return fgIsA;
}

} // namespace snd
namespace snd {
//______________________________________________________________________________
void DataManager::Streamer(TBuffer &R__b)
{
   // Stream an object of class snd::DataManager.

   if (R__b.IsReading()) {
      R__b.ReadClassBuffer(snd::DataManager::Class(),this);
   } else {
      R__b.WriteClassBuffer(snd::DataManager::Class(),this);
   }
}

} // namespace snd
namespace ROOT {
   // Wrappers around operator new
   static void *new_sndcLcLDataManager(void *p) {
      return  p ? ::new(static_cast<::ROOT::Internal::TOperatorNewHelper*>(p)) ::snd::DataManager : new ::snd::DataManager;
   }
   static void *newArray_sndcLcLDataManager(Long_t nElements, void *p) {
      return p ? ::new(static_cast<::ROOT::Internal::TOperatorNewHelper*>(p)) ::snd::DataManager[nElements] : new ::snd::DataManager[nElements];
   }
   // Wrapper around operator delete
   static void delete_sndcLcLDataManager(void *p) {
      delete (static_cast<::snd::DataManager*>(p));
   }
   static void deleteArray_sndcLcLDataManager(void *p) {
      delete [] (static_cast<::snd::DataManager*>(p));
   }
   static void destruct_sndcLcLDataManager(void *p) {
      typedef ::snd::DataManager current_t;
      (static_cast<current_t*>(p))->~current_t();
   }
} // end of namespace ROOT for class ::snd::DataManager

namespace ROOT {
   static TClass *vectorlEstringgR_Dictionary();
   static void vectorlEstringgR_TClassManip(TClass*);
   static void *new_vectorlEstringgR(void *p = nullptr);
   static void *newArray_vectorlEstringgR(Long_t size, void *p);
   static void delete_vectorlEstringgR(void *p);
   static void deleteArray_vectorlEstringgR(void *p);
   static void destruct_vectorlEstringgR(void *p);

   // Function generating the singleton type initializer
   static TGenericClassInfo *GenerateInitInstanceLocal(const vector<string>*)
   {
      vector<string> *ptr = nullptr;
      static ::TVirtualIsAProxy* isa_proxy = new ::TIsAProxy(typeid(vector<string>));
      static ::ROOT::TGenericClassInfo 
         instance("vector<string>", -2, "vector", 389,
                  typeid(vector<string>), ::ROOT::Internal::DefineBehavior(ptr, ptr),
                  &vectorlEstringgR_Dictionary, isa_proxy, 0,
                  sizeof(vector<string>) );
      instance.SetNew(&new_vectorlEstringgR);
      instance.SetNewArray(&newArray_vectorlEstringgR);
      instance.SetDelete(&delete_vectorlEstringgR);
      instance.SetDeleteArray(&deleteArray_vectorlEstringgR);
      instance.SetDestructor(&destruct_vectorlEstringgR);
      instance.AdoptCollectionProxyInfo(TCollectionProxyInfo::Generate(TCollectionProxyInfo::Pushback< vector<string> >()));

      instance.AdoptAlternate(::ROOT::AddClassAlternate("vector<string>","std::vector<std::__cxx11::basic_string<char, std::char_traits<char>, std::allocator<char> >, std::allocator<std::__cxx11::basic_string<char, std::char_traits<char>, std::allocator<char> > > >"));
      return &instance;
   }
   // Static variable to force the class initialization
   static ::ROOT::TGenericClassInfo *_R__UNIQUE_DICT_(Init) = GenerateInitInstanceLocal(static_cast<const vector<string>*>(nullptr)); R__UseDummy(_R__UNIQUE_DICT_(Init));

   // Dictionary for non-ClassDef classes
   static TClass *vectorlEstringgR_Dictionary() {
      TClass* theClass =::ROOT::GenerateInitInstanceLocal(static_cast<const vector<string>*>(nullptr))->GetClass();
      vectorlEstringgR_TClassManip(theClass);
   return theClass;
   }

   static void vectorlEstringgR_TClassManip(TClass* ){
   }

} // end of namespace ROOT

namespace ROOT {
   // Wrappers around operator new
   static void *new_vectorlEstringgR(void *p) {
      return  p ? ::new(static_cast<::ROOT::Internal::TOperatorNewHelper*>(p)) vector<string> : new vector<string>;
   }
   static void *newArray_vectorlEstringgR(Long_t nElements, void *p) {
      return p ? ::new(static_cast<::ROOT::Internal::TOperatorNewHelper*>(p)) vector<string>[nElements] : new vector<string>[nElements];
   }
   // Wrapper around operator delete
   static void delete_vectorlEstringgR(void *p) {
      delete (static_cast<vector<string>*>(p));
   }
   static void deleteArray_vectorlEstringgR(void *p) {
      delete [] (static_cast<vector<string>*>(p));
   }
   static void destruct_vectorlEstringgR(void *p) {
      typedef vector<string> current_t;
      (static_cast<current_t*>(p))->~current_t();
   }
} // end of namespace ROOT for class vector<string>

namespace ROOT {
   static TClass *unordered_setlEstringgR_Dictionary();
   static void unordered_setlEstringgR_TClassManip(TClass*);
   static void *new_unordered_setlEstringgR(void *p = nullptr);
   static void *newArray_unordered_setlEstringgR(Long_t size, void *p);
   static void delete_unordered_setlEstringgR(void *p);
   static void deleteArray_unordered_setlEstringgR(void *p);
   static void destruct_unordered_setlEstringgR(void *p);

   // Function generating the singleton type initializer
   static TGenericClassInfo *GenerateInitInstanceLocal(const unordered_set<string>*)
   {
      unordered_set<string> *ptr = nullptr;
      static ::TVirtualIsAProxy* isa_proxy = new ::TIsAProxy(typeid(unordered_set<string>));
      static ::ROOT::TGenericClassInfo 
         instance("unordered_set<string>", -2, "unordered_set", 97,
                  typeid(unordered_set<string>), ::ROOT::Internal::DefineBehavior(ptr, ptr),
                  &unordered_setlEstringgR_Dictionary, isa_proxy, 0,
                  sizeof(unordered_set<string>) );
      instance.SetNew(&new_unordered_setlEstringgR);
      instance.SetNewArray(&newArray_unordered_setlEstringgR);
      instance.SetDelete(&delete_unordered_setlEstringgR);
      instance.SetDeleteArray(&deleteArray_unordered_setlEstringgR);
      instance.SetDestructor(&destruct_unordered_setlEstringgR);
      instance.AdoptCollectionProxyInfo(TCollectionProxyInfo::Generate(TCollectionProxyInfo::Insert< unordered_set<string> >()));

      instance.AdoptAlternate(::ROOT::AddClassAlternate("unordered_set<string>","std::unordered_set<std::__cxx11::basic_string<char, std::char_traits<char>, std::allocator<char> >, std::hash<std::__cxx11::basic_string<char, std::char_traits<char>, std::allocator<char> > >, std::equal_to<std::__cxx11::basic_string<char, std::char_traits<char>, std::allocator<char> > >, std::allocator<std::__cxx11::basic_string<char, std::char_traits<char>, std::allocator<char> > > >"));
      return &instance;
   }
   // Static variable to force the class initialization
   static ::ROOT::TGenericClassInfo *_R__UNIQUE_DICT_(Init) = GenerateInitInstanceLocal(static_cast<const unordered_set<string>*>(nullptr)); R__UseDummy(_R__UNIQUE_DICT_(Init));

   // Dictionary for non-ClassDef classes
   static TClass *unordered_setlEstringgR_Dictionary() {
      TClass* theClass =::ROOT::GenerateInitInstanceLocal(static_cast<const unordered_set<string>*>(nullptr))->GetClass();
      unordered_setlEstringgR_TClassManip(theClass);
   return theClass;
   }

   static void unordered_setlEstringgR_TClassManip(TClass* ){
   }

} // end of namespace ROOT

namespace ROOT {
   // Wrappers around operator new
   static void *new_unordered_setlEstringgR(void *p) {
      return  p ? ::new(static_cast<::ROOT::Internal::TOperatorNewHelper*>(p)) unordered_set<string> : new unordered_set<string>;
   }
   static void *newArray_unordered_setlEstringgR(Long_t nElements, void *p) {
      return p ? ::new(static_cast<::ROOT::Internal::TOperatorNewHelper*>(p)) unordered_set<string>[nElements] : new unordered_set<string>[nElements];
   }
   // Wrapper around operator delete
   static void delete_unordered_setlEstringgR(void *p) {
      delete (static_cast<unordered_set<string>*>(p));
   }
   static void deleteArray_unordered_setlEstringgR(void *p) {
      delete [] (static_cast<unordered_set<string>*>(p));
   }
   static void destruct_unordered_setlEstringgR(void *p) {
      typedef unordered_set<string> current_t;
      (static_cast<current_t*>(p))->~current_t();
   }
} // end of namespace ROOT for class unordered_set<string>

namespace ROOT {
   // Registration Schema evolution read functions
   int RecordReadRules_libsnd_analysis() {
      return 0;
   }
   static int _R__UNIQUE_DICT_(ReadRules_libsnd_analysis) = RecordReadRules_libsnd_analysis();R__UseDummy(_R__UNIQUE_DICT_(ReadRules_libsnd_analysis));
} // namespace ROOT
namespace {
  void TriggerDictionaryInitialization_libsnd_analysis_Impl() {
    static const char* headers[] = {
"DataManager.h",
nullptr
    };
    static const char* includePaths[] = {
"/afs/cern.ch/work/i/idioniso/sndVetoUS/analysis",
"/afs/cern.ch/work/i/idioniso/sndVetoUS",
"/cvmfs/sndlhc.cern.ch/SNDLHC-2025/Oct7/sw/slc9_x86-64/ROOT/v6-36-04-alice1-local1/include",
"/afs/cern.ch/user/i/idioniso/snd_master/sw-vetoUS/slc9_x86-64/sndsw/master-local1/include",
"/cvmfs/sndlhc.cern.ch/SNDLHC-2025/Oct7/sw/slc9_x86-64/FairRoot/v19.0.0-local1/include",
"/cvmfs/sndlhc.cern.ch/SNDLHC-2025/Oct7/sw/slc9_x86-64/FairLogger/v1.9.0-local1/include",
"/cvmfs/sndlhc.cern.ch/SNDLHC-2025/Oct7/sw/slc9_x86-64/fmt/7.1.0-local1/include",
"/cvmfs/sndlhc.cern.ch/SNDLHC-2025/Oct7/sw/slc9_x86-64/VMC/v2-0-local1/include/vmc",
"/cvmfs/sndlhc.cern.ch/SNDLHC-2025/Oct7/sw/slc9_x86-64/ROOT/v6-36-04-alice1-local1/include/",
"/afs/cern.ch/work/i/idioniso/sndVetoUS/build/analysis/",
nullptr
    };
    static const char* fwdDeclCode = R"DICTFWDDCLS(
#line 1 "libsnd_analysis dictionary forward declarations' payload"
#pragma clang diagnostic ignored "-Wkeyword-compat"
#pragma clang diagnostic ignored "-Wignored-attributes"
#pragma clang diagnostic ignored "-Wreturn-type-c-linkage"
extern int __Cling_AutoLoading_Map;
namespace snd{class __attribute__((annotate("$clingAutoload$DataManager.h")))  DataManager;}
)DICTFWDDCLS";
    static const char* payloadCode = R"DICTPAYLOAD(
#line 1 "libsnd_analysis dictionary payload"


#define _BACKWARD_BACKWARD_WARNING_H
// Inline headers
#include "DataManager.h"

#undef  _BACKWARD_BACKWARD_WARNING_H
)DICTPAYLOAD";
    static const char* classesHeaders[] = {
"snd::DataManager", payloadCode, "@",
nullptr
};
    static bool isInitialized = false;
    if (!isInitialized) {
      TROOT::RegisterModule("libsnd_analysis",
        headers, includePaths, payloadCode, fwdDeclCode,
        TriggerDictionaryInitialization_libsnd_analysis_Impl, {}, classesHeaders, /*hasCxxModule*/false);
      isInitialized = true;
    }
  }
  static struct DictInit {
    DictInit() {
      TriggerDictionaryInitialization_libsnd_analysis_Impl();
    }
  } __TheDictionaryInitializer;
}
void TriggerDictionaryInitialization_libsnd_analysis() {
  TriggerDictionaryInitialization_libsnd_analysis_Impl();
}
